from __future__ import annotations

import base64
import io
from collections import Counter
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageSequence

from app.data.blocks import BlockColor, by_id
from app.map_palette import MapColorCandidate, create_map_palette
from app.models import ConvertSettings, FitMode, MapVariant, TransparentMode
from app.palette import select_blocks


AIR_ID = "minecraft:air"


@dataclass
class ConvertedArt:
    block_grid: list[list[str]]
    height_grid: list[list[int]]
    preview_png: bytes
    block_preview_png: bytes | None
    map_preview_png: bytes | None
    materials: Counter[str]
    air_count: int
    width: int
    height: int
    depth: int
    placements: list[dict[str, int | str]] | None = None


def first_frame(image_bytes: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(image_bytes))
    frame = next(ImageSequence.Iterator(image)).convert("RGBA")
    return frame


def resize_image(image: Image.Image, settings: ConvertSettings) -> Image.Image:
    width, height = output_size(settings, image.size)
    if settings.fit_mode == FitMode.STRETCH:
        return image.resize((width, height), Image.Resampling.LANCZOS)

    src_w, src_h = image.size
    scale = max(width / src_w, height / src_h) if settings.fit_mode == FitMode.COVER else min(width / src_w, height / src_h)
    scaled = image.resize((max(1, round(src_w * scale)), max(1, round(src_h * scale))), Image.Resampling.LANCZOS)

    if settings.fit_mode == FitMode.COVER:
        left = max(0, (scaled.width - width) // 2)
        top = max(0, (scaled.height - height) // 2)
        return scaled.crop((left, top, left + width, top + height))

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
    return canvas


def output_size(settings: ConvertSettings, original_size: tuple[int, int]) -> tuple[int, int]:
    if settings.art_mode.value == "map":
        return settings.map_columns * 128, settings.map_rows * 128
    if not settings.lock_aspect:
        return settings.target_width, settings.target_height
    src_w, src_h = original_size
    ratio = src_h / src_w if src_w else 1
    return settings.target_width, max(1, round(settings.target_width * ratio))


def nearest_block_index(pixel: np.ndarray, palette_values: np.ndarray) -> tuple[int, float]:
    weights = np.array([0.30, 0.59, 0.11])
    distances = np.sum(((palette_values - pixel) ** 2) * weights, axis=1)
    idx = int(np.argmin(distances))
    return idx, float(np.sqrt(distances[idx]))


def match_pixels(image: Image.Image, blocks: list[BlockColor], settings: ConvertSettings) -> tuple[list[list[str]], Counter[str], int]:
    rgba = np.array(image).astype(np.float64)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    palette_rgb = np.array([block.rgb for block in blocks], dtype=np.float64)
    block_ids = [block.id for block in blocks]
    grid: list[list[str]] = []
    air_count = 0

    work = rgb.copy()
    for y in range(image.height):
        row: list[str] = []
        for x in range(image.width):
            if alpha[y, x] < 8 and settings.transparent_mode == TransparentMode.AIR:
                row.append(AIR_ID)
                air_count += 1
                continue
            if alpha[y, x] < 8 and settings.transparent_mode == TransparentMode.WHITE:
                work[y, x] = np.array([255, 255, 255])
            if alpha[y, x] < 8 and settings.transparent_mode == TransparentMode.BLACK:
                work[y, x] = np.array([0, 0, 0])

            color = np.clip(work[y, x], 0, 255)
            idx, _distance = nearest_block_index(color, palette_rgb)
            block_id = settings.replacements.get(block_ids[idx], block_ids[idx])
            row.append(block_id)

        grid.append(row)
    return grid, count_materials(grid), air_count


def match_map_art(
    image: Image.Image,
    blocks: list[BlockColor],
    settings: ConvertSettings,
) -> tuple[list[list[str]], list[list[int]], list[dict[str, int | str]], Counter[str], int, bytes, bytes, int]:
    candidates = create_map_palette(blocks, settings.map_variant)
    if not candidates:
        raise ValueError("No map-art colors are available for the selected palette.")

    rgba = np.array(image).astype(np.float64)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    palette_rgb = np.array([candidate.map_rgb for candidate in candidates], dtype=np.float64)
    work = rgb.copy()
    chosen: list[list[MapColorCandidate | None]] = []
    block_grid: list[list[str]] = []
    map_preview = Image.new("RGBA", image.size, (0, 0, 0, 0))
    block_preview = Image.new("RGBA", image.size, (0, 0, 0, 0))
    map_pixels = map_preview.load()
    block_pixels = block_preview.load()
    air_count = 0

    for y in range(image.height):
        chosen_row: list[MapColorCandidate | None] = []
        block_row: list[str] = []
        for x in range(image.width):
            if alpha[y, x] < 8 and settings.transparent_mode == TransparentMode.AIR:
                chosen_row.append(None)
                block_row.append(AIR_ID)
                air_count += 1
                continue
            if alpha[y, x] < 8 and settings.transparent_mode == TransparentMode.WHITE:
                work[y, x] = np.array([255, 255, 255])
            if alpha[y, x] < 8 and settings.transparent_mode == TransparentMode.BLACK:
                work[y, x] = np.array([0, 0, 0])

            color = np.clip(work[y, x], 0, 255)
            idx, _distance = nearest_map_color_index(color, palette_rgb)
            candidate = candidates[idx]
            chosen_row.append(candidate)
            block_row.append(candidate.block_id)
            map_pixels[x, y] = (*candidate.map_rgb, 255)
            block_pixels[x, y] = (*candidate.block_rgb, 255)
        chosen.append(chosen_row)
        block_grid.append(block_row)

    height_grid = map_height_grid(chosen, settings)
    placements = map_placements(chosen, height_grid)
    materials = count_placement_materials(placements)
    depth = max((int(placement["level"]) for placement in placements), default=0) + 1
    return (
        block_grid,
        height_grid,
        placements,
        materials,
        air_count,
        render_preview_image(map_preview, settings.show_grid),
        render_preview_image(block_preview, settings.show_grid),
        depth,
    )


def nearest_map_color_index(pixel: np.ndarray, palette_values: np.ndarray) -> tuple[int, float]:
    weights = np.array([0.30, 0.59, 0.11])
    distances = np.sum(((palette_values - pixel) ** 2) * weights, axis=1)
    idx = int(np.argmin(distances))
    return idx, float(np.sqrt(distances[idx]))


def map_height_grid(chosen: list[list[MapColorCandidate | None]], settings: ConvertSettings) -> list[list[int]]:
    height = len(chosen)
    width = len(chosen[0]) if chosen else 0
    grid = [[0 for _ in range(width)] for _ in range(height)]
    if settings.map_variant != MapVariant.STAIRS:
        return grid
    min_level = 0
    for x in range(width):
        level = 0
        for y in range(height):
            candidate = chosen[y][x]
            if candidate and not candidate.is_water:
                if candidate.shade == 2:
                    level += 1
                elif candidate.shade == 0:
                    level -= 1
            grid[y][x] = level
            min_level = min(min_level, level)
    if min_level < 0:
        grid = [[level - min_level for level in row] for row in grid]
    return grid


def map_placements(chosen: list[list[MapColorCandidate | None]], height_grid: list[list[int]]) -> list[dict[str, int | str]]:
    placements: list[dict[str, int | str]] = []
    for y, row in enumerate(chosen):
        for x, candidate in enumerate(row):
            if candidate is None:
                continue
            base_level = height_grid[y][x]
            if candidate.is_water:
                placements.append({"x": x, "y": y, "level": base_level, "block_id": "minecraft:stone"})
                for level in range(base_level + 1, base_level + candidate.water_depth + 1):
                    placements.append({"x": x, "y": y, "level": level, "block_id": candidate.block_id})
            else:
                placements.append({"x": x, "y": y, "level": base_level, "block_id": candidate.block_id})
    return placements


def count_placement_materials(placements: list[dict[str, int | str]]) -> Counter[str]:
    materials: Counter[str] = Counter()
    for placement in placements:
        block_id = str(placement["block_id"])
        if block_id != AIR_ID:
            materials[block_id] += 1
    return materials


def count_materials(grid: list[list[str]]) -> Counter[str]:
    materials: Counter[str] = Counter()
    for row in grid:
        for block_id in row:
            if block_id != AIR_ID:
                materials[block_id] += 1
    return materials


def height_grid_for(image: Image.Image, settings: ConvertSettings) -> list[list[int]]:
    if settings.art_mode.value != "map" or settings.map_variant != MapVariant.STAIRS:
        return [[0 for _ in range(image.width)] for _ in range(image.height)]
    rgb = np.array(image.convert("RGB")).astype(np.float64)
    luminance = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    levels = np.clip(np.rint(luminance / 255 * 3), 0, 3).astype(int)
    return levels.tolist()


def render_preview(grid: list[list[str]], show_grid: bool) -> bytes:
    index = by_id()
    scale = 1
    width = len(grid[0]) if grid else 0
    height = len(grid)
    image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    pixels = image.load()
    for y, row in enumerate(grid):
        for x, block_id in enumerate(row):
            if block_id == AIR_ID:
                pixels[x, y] = (0, 0, 0, 0)
            else:
                r, g, b = index[base_block_id(block_id)].rgb
                pixels[x, y] = (r, g, b, 255)
    return render_preview_image(image, show_grid)


def render_preview_image(image: Image.Image, show_grid: bool) -> bytes:
    width, height = image.size
    max_side = 768
    if max(width, height) < max_side:
        factor = max(1, min(max_side // max(width, height), 12))
        image = image.resize((width * factor, height * factor), Image.Resampling.NEAREST)
        if show_grid and factor >= 6:
            draw = ImageDraw.Draw(image)
            line = (20, 24, 28, 70)
            for x in range(0, image.width + 1, factor):
                draw.line((x, 0, x, image.height), fill=line)
            for y in range(0, image.height + 1, factor):
                draw.line((0, y, image.width, y), fill=line)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def base_block_id(block_id: str) -> str:
    return block_id.split("[", 1)[0]


def convert_image(image_bytes: bytes, settings: ConvertSettings) -> ConvertedArt:
    source = first_frame(image_bytes)
    resized = resize_image(source, settings)
    blocks = select_blocks(settings)
    if not blocks:
        raise ValueError("No blocks are available for the selected palette.")
    if settings.art_mode.value == "map":
        grid, heights, placements, materials, air_count, map_preview, block_preview, depth = match_map_art(resized, blocks, settings)
        preview = block_preview if settings.map_preview.value == "blocks" else map_preview
        return ConvertedArt(
            block_grid=grid,
            height_grid=heights,
            preview_png=preview,
            block_preview_png=block_preview,
            map_preview_png=map_preview,
            materials=materials,
            air_count=air_count,
            width=resized.width,
            height=resized.height,
            depth=depth,
            placements=placements,
        )
    grid, materials, air_count = match_pixels(resized, blocks, settings)
    heights = height_grid_for(resized, settings)
    depth = max(max(row) for row in heights) + 1 if heights else 1
    preview = render_preview(grid, settings.show_grid)
    return ConvertedArt(grid, heights, preview, None, None, materials, air_count, resized.width, resized.height, depth)


def data_url_png(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
