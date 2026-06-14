from __future__ import annotations

import base64
import io
from collections import Counter
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageSequence

from app.data.blocks import BlockColor, by_id
from app.models import ConvertSettings, FitMode, MapVariant, QualityMode, TransparentMode
from app.palette import select_blocks


AIR_ID = "minecraft:air"


@dataclass
class ConvertedArt:
    block_grid: list[list[str]]
    height_grid: list[list[int]]
    preview_png: bytes
    materials: Counter[str]
    air_count: int
    width: int
    height: int
    depth: int


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


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(np.float64) / 255.0
    rgb = np.where(rgb > 0.04045, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    matrix = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    xyz = rgb @ matrix.T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    f = np.where(xyz > delta**3, np.cbrt(xyz), xyz / (3 * delta**2) + 4 / 29)
    l = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([l, a, b], axis=-1)


def nearest_block_index(pixel: np.ndarray, palette_values: np.ndarray, quality: QualityMode) -> int:
    if quality == QualityMode.FAST:
        weights = np.array([0.30, 0.59, 0.11])
        distances = np.sum(((palette_values - pixel) ** 2) * weights, axis=1)
    else:
        pixel_lab = srgb_to_lab(pixel.reshape(1, 3))[0]
        palette_lab = srgb_to_lab(palette_values)
        distances = np.sum((palette_lab - pixel_lab) ** 2, axis=1)
    return int(np.argmin(distances))


def match_pixels(image: Image.Image, blocks: list[BlockColor], settings: ConvertSettings) -> tuple[list[list[str]], Counter[str], int]:
    rgba = np.array(image).astype(np.float64)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    palette_rgb = np.array([block.rgb for block in blocks], dtype=np.float64)
    block_ids = [block.id for block in blocks]
    grid: list[list[str]] = []
    materials: Counter[str] = Counter()
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

            idx = nearest_block_index(np.clip(work[y, x], 0, 255), palette_rgb, settings.quality)
            block_id = settings.replacements.get(block_ids[idx], block_ids[idx])
            row.append(block_id)
            materials[block_id] += 1

            if settings.quality == QualityMode.HIGH:
                quantized = np.array(blocks[idx].rgb, dtype=np.float64)
                error = work[y, x] - quantized
                if x + 1 < image.width:
                    work[y, x + 1] += error * 7 / 16
                if y + 1 < image.height:
                    if x > 0:
                        work[y + 1, x - 1] += error * 3 / 16
                    work[y + 1, x] += error * 5 / 16
                    if x + 1 < image.width:
                        work[y + 1, x + 1] += error * 1 / 16
        grid.append(row)
    return grid, materials, air_count


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
                r, g, b = index[block_id].rgb
                pixels[x, y] = (r, g, b, 255)
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


def convert_image(image_bytes: bytes, settings: ConvertSettings) -> ConvertedArt:
    source = first_frame(image_bytes)
    resized = resize_image(source, settings)
    blocks = select_blocks(settings)
    if not blocks:
        raise ValueError("No blocks are available for the selected palette.")
    grid, materials, air_count = match_pixels(resized, blocks, settings)
    heights = height_grid_for(resized, settings)
    depth = max(max(row) for row in heights) + 1 if heights else 1
    preview = render_preview(grid, settings.show_grid)
    return ConvertedArt(grid, heights, preview, materials, air_count, resized.width, resized.height, depth)


def data_url_png(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
