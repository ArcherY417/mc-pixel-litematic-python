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
DITHER_STRENGTH = 0.34
DITHER_ERROR_LIMIT = 42.0
BAYER_4X4 = np.array([0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5], dtype=np.float64).reshape(4, 4)
BAYER_4X4 = (BAYER_4X4 + 0.5) / 16


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


def nearest_block_index(
    pixel: np.ndarray,
    palette_values: np.ndarray,
    palette_lab: np.ndarray,
    palette_hsl: np.ndarray,
    quality: QualityMode,
    x: int,
    y: int,
) -> tuple[int, float]:
    if quality == QualityMode.FAST:
        weights = np.array([0.30, 0.59, 0.11])
        distances = np.sum(((palette_values - pixel) ** 2) * weights, axis=1)
    else:
        pixel_lab = srgb_to_lab(pixel.reshape(1, 3))[0]
        lab_distances = np.sum((palette_lab - pixel_lab) ** 2, axis=1)
        distances = hue_aware_lab_distances(pixel, palette_hsl, lab_distances)
    idx = int(np.argmin(distances))
    if quality == QualityMode.HIGH:
        idx = pastel_lighten_index(pixel, idx, palette_hsl, x, y)
        idx = pastel_tint_index(pixel, idx, palette_hsl, x, y)
    return idx, float(np.sqrt(distances[idx]))


def pastel_lighten_index(pixel: np.ndarray, best_idx: int, palette_hsl: np.ndarray, x: int, y: int) -> int:
    source_h, source_s, source_l = rgb_to_hsl(pixel)
    _best_h, best_s, best_l = palette_hsl[best_idx]
    lightness_gap = source_l - best_l
    if source_l < 0.62 or lightness_gap < 0.04:
        return best_idx
    warm_pastel = (source_h <= 52 or source_h >= 350) and source_l > 0.64

    candidate_mask = (palette_hsl[:, 1] <= 0.09) & (palette_hsl[:, 2] > best_l + 0.05)
    if not np.any(candidate_mask):
        return best_idx

    scores = np.abs(palette_hsl[:, 2] - source_l) * 100 + palette_hsl[:, 1] * 30
    scores = np.where(candidate_mask, scores, np.inf)
    neutral_idx = int(np.argmin(scores))
    if warm_pastel:
        return neutral_idx if source_l > 0.79 else best_idx

    neutral_l = float(palette_hsl[neutral_idx, 2])
    denominator = max(0.001, neutral_l - best_l)
    amount = clamp01(lightness_gap / denominator) * (0.58 if source_s > 0.45 else 0.72)
    return neutral_idx if amount > BAYER_4X4[(y + 1) % 4, (x + 2) % 4] else best_idx


def pastel_tint_index(pixel: np.ndarray, best_idx: int, palette_hsl: np.ndarray, x: int, y: int) -> int:
    chroma = float(np.max(pixel) - np.min(pixel))
    source_h, source_s, source_l = rgb_to_hsl(pixel)
    if chroma < 14 or source_s < 0.08 or source_l < 0.48:
        return best_idx
    if (source_h <= 52 or source_h >= 350) and source_l > 0.55:
        return best_idx

    best_h, best_s, _ = palette_hsl[best_idx]
    if best_s >= 0.09 and float(hue_distance_array(source_h, np.array([best_h]))[0]) < 54:
        return best_idx

    hue_diff = hue_distance_array(source_h, palette_hsl[:, 0])
    candidate_mask = (palette_hsl[:, 1] >= 0.12) & (hue_diff <= 50)
    if not np.any(candidate_mask):
        return best_idx

    lightness_gap = np.abs(source_l - palette_hsl[:, 2])
    scores = hue_diff * 2.4 + lightness_gap * 120 - palette_hsl[:, 1] * 18
    scores = np.where(candidate_mask, scores, np.inf)
    tint_idx = int(np.argmin(scores))
    tint_lightness_gap = float(lightness_gap[tint_idx])
    neutral_base = best_s < 0.09
    base_amount = (
        clamp01((chroma - 12) / 86)
        * clamp01((source_l - 0.45) / 0.5)
        * clamp01(1 - max(0.0, tint_lightness_gap - 0.14) / 0.5)
        * 0.58
    )
    minimum_pastel_tint = clamp01((chroma - 16) / 70) * 0.62 if neutral_base and source_l > 0.68 else 0.0
    amount = max(base_amount, minimum_pastel_tint)
    return tint_idx if amount > BAYER_4X4[y % 4, x % 4] else best_idx


def hue_aware_lab_distances(source: np.ndarray, palette_hsl: np.ndarray, lab_squared: np.ndarray) -> np.ndarray:
    source_h, source_s, source_l = rgb_to_hsl(source)
    if source_s < 0.045:
        return lab_squared

    hue_diff = hue_distance_array(source_h, palette_hsl[:, 0])
    color_intent = clamp01((source_s - 0.045) / 0.22) * (1.18 if source_l > 0.55 else 1.0)
    candidate_is_neutral = palette_hsl[:, 1] < 0.08
    candidate_has_color = palette_hsl[:, 1] > 0.08
    near_hue = np.clip(1 - hue_diff / 48, 0.0, 1.0)
    far_hue = np.clip((hue_diff - 58) / 92, 0.0, 1.0)

    penalty = (hue_diff / 180) ** 2 * (220 + 300 * color_intent)
    penalty = penalty + np.where(candidate_is_neutral, (260.0 if source_l > 0.55 else 150.0) * color_intent, 0.0)
    penalty = penalty - np.where(candidate_has_color, near_hue * (190 + 160 * color_intent) * color_intent, 0.0)
    penalty = penalty + np.where(candidate_has_color, far_hue * 260 * color_intent, 0.0)
    return np.maximum(0.0, lab_squared + penalty)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def hue_distance_array(a: float, b: np.ndarray) -> np.ndarray:
    diff = np.abs(a - b) % 360
    return np.minimum(diff, 360 - diff)


def rgb_to_hsl(rgb: np.ndarray) -> tuple[float, float, float]:
    r, g, b = [float(channel) / 255.0 for channel in rgb]
    max_v = max(r, g, b)
    min_v = min(r, g, b)
    lightness = (max_v + min_v) / 2
    if max_v == min_v:
        return 0.0, 0.0, lightness
    delta = max_v - min_v
    saturation = delta / (2 - max_v - min_v) if lightness > 0.5 else delta / (max_v + min_v)
    if max_v == r:
        hue = (g - b) / delta + (6 if g < b else 0)
    elif max_v == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return hue * 60, saturation, lightness


def rgb_array_to_hsl(rgb: np.ndarray) -> np.ndarray:
    values = rgb.astype(np.float64) / 255.0
    r = values[:, 0]
    g = values[:, 1]
    b = values[:, 2]
    max_v = np.max(values, axis=1)
    min_v = np.min(values, axis=1)
    lightness = (max_v + min_v) / 2
    delta = max_v - min_v
    saturation = np.zeros_like(lightness)
    non_gray = delta > 0
    saturation[non_gray] = np.where(
        lightness[non_gray] > 0.5,
        delta[non_gray] / (2 - max_v[non_gray] - min_v[non_gray]),
        delta[non_gray] / (max_v[non_gray] + min_v[non_gray]),
    )

    hue = np.zeros_like(lightness)
    red = non_gray & (max_v == r)
    green = non_gray & (max_v == g)
    blue = non_gray & (max_v == b)
    hue[red] = (g[red] - b[red]) / delta[red] + np.where(g[red] < b[red], 6, 0)
    hue[green] = (b[green] - r[green]) / delta[green] + 2
    hue[blue] = (r[blue] - g[blue]) / delta[blue] + 4
    hue *= 60
    return np.stack([hue, saturation, lightness], axis=1)


def match_pixels(image: Image.Image, blocks: list[BlockColor], settings: ConvertSettings) -> tuple[list[list[str]], Counter[str], int]:
    rgba = np.array(image).astype(np.float64)
    rgb = rgba[..., :3]
    alpha = rgba[..., 3]
    palette_rgb = np.array([block.rgb for block in blocks], dtype=np.float64)
    palette_lab = srgb_to_lab(palette_rgb)
    palette_hsl = rgb_array_to_hsl(palette_rgb)
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
            idx, distance = nearest_block_index(color, palette_rgb, palette_lab, palette_hsl, settings.quality, x, y)
            block_id = settings.replacements.get(block_ids[idx], block_ids[idx])
            row.append(block_id)

            if settings.quality == QualityMode.HIGH and should_diffuse(color, distance):
                quantized = np.array(blocks[idx].rgb, dtype=np.float64)
                error = np.clip(work[y, x] - quantized, -DITHER_ERROR_LIMIT, DITHER_ERROR_LIMIT)
                if x + 1 < image.width:
                    work[y, x + 1] += error * 7 / 16 * DITHER_STRENGTH
                if y + 1 < image.height:
                    if x > 0:
                        work[y + 1, x - 1] += error * 3 / 16 * DITHER_STRENGTH
                    work[y + 1, x] += error * 5 / 16 * DITHER_STRENGTH
                    if x + 1 < image.width:
                        work[y + 1, x + 1] += error * 1 / 16 * DITHER_STRENGTH
        grid.append(row)
    if settings.quality == QualityMode.HIGH:
        grid = despeckle_grid(grid)
    return grid, count_materials(grid), air_count


def should_diffuse(color: np.ndarray, lab_distance: float) -> bool:
    luminance = float(color[0] * 0.2126 + color[1] * 0.7152 + color[2] * 0.0722)
    chroma = float(np.max(color) - np.min(color))
    if luminance > 205 and chroma < 42:
        return False
    if lab_distance < 9 or lab_distance > 46:
        return False
    return True


def despeckle_grid(grid: list[list[str]]) -> list[list[str]]:
    index = by_id()
    height = len(grid)
    width = len(grid[0]) if grid else 0
    output = [row.copy() for row in grid]
    for y in range(height):
        for x in range(width):
            current = grid[y][x]
            if current == AIR_ID:
                continue
            counts: Counter[str] = Counter()
            for yy in range(y - 1, y + 2):
                for xx in range(x - 1, x + 2):
                    if xx == x and yy == y:
                        continue
                    if yy < 0 or yy >= height or xx < 0 or xx >= width:
                        continue
                    neighbor = grid[yy][xx]
                    if neighbor != AIR_ID:
                        counts[neighbor] += 1
            if not counts:
                continue
            majority, majority_count = counts.most_common(1)[0]
            if majority == current or majority_count < 5:
                continue
            if is_protected_dark_line(current, majority, index):
                continue
            output[y][x] = majority
    return output


def is_protected_dark_line(current_id: str, replacement_id: str, index: dict[str, object]) -> bool:
    current = index.get(current_id)
    replacement = index.get(replacement_id)
    if current is None or replacement is None:
        return False
    current_luma = current.rgb[0] * 0.2126 + current.rgb[1] * 0.7152 + current.rgb[2] * 0.0722
    replacement_luma = replacement.rgb[0] * 0.2126 + replacement.rgb[1] * 0.7152 + replacement.rgb[2] * 0.0722
    return current_luma < 80 and replacement_luma > 125


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
