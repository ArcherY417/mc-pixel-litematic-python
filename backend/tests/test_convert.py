from __future__ import annotations

import io
from pathlib import Path

from litemapy import Schematic
from PIL import Image

from app.image_convert import convert_image
from app.litematic_export import create_litematic, pixel_to_region, schematic_dimensions
from app.models import BuildPlane, ConvertSettings, Direction, PaletteMode, QualityMode


def png_bytes(pixels: list[list[tuple[int, int, int, int]]]) -> bytes:
    height = len(pixels)
    width = len(pixels[0])
    image = Image.new("RGBA", (width, height))
    for y, row in enumerate(pixels):
        for x, color in enumerate(row):
            image.putpixel((x, y), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_transparent_pixels_become_air() -> None:
    settings = ConvertSettings(target_width=2, target_height=1, lock_aspect=False, palette_mode=PaletteMode.CONCRETE)
    art = convert_image(png_bytes([[(255, 0, 0, 255), (0, 0, 0, 0)]]), settings)
    assert art.width == 2
    assert art.air_count == 1
    assert art.block_grid[0][1] == "minecraft:air"
    assert sum(art.materials.values()) == 1


def test_quality_modes_return_valid_materials() -> None:
    image = png_bytes([[(245, 20, 20, 255), (40, 120, 220, 255)]])
    fast = convert_image(image, ConvertSettings(target_width=2, target_height=1, lock_aspect=False, quality=QualityMode.FAST))
    high = convert_image(image, ConvertSettings(target_width=2, target_height=1, lock_aspect=False, quality=QualityMode.HIGH))
    assert len(fast.block_grid[0]) == 2
    assert len(high.block_grid[0]) == 2
    assert sum(fast.materials.values()) == 2
    assert sum(high.materials.values()) == 2


def test_wall_direction_coordinate_mapping() -> None:
    settings = ConvertSettings(target_width=2, target_height=2, lock_aspect=False, build_plane=BuildPlane.WALL, direction=Direction.SOUTH)
    art = convert_image(png_bytes([[(255, 0, 0, 255), (0, 255, 0, 255)], [(0, 0, 255, 255), (255, 255, 0, 255)]]), settings)
    assert schematic_dimensions(art, settings) == (2, 2, 1)
    assert pixel_to_region(0, 0, art, settings) == (1, 1, 0)
    assert pixel_to_region(1, 1, art, settings) == (0, 0, 0)


def test_floor_east_coordinate_mapping() -> None:
    settings = ConvertSettings(target_width=3, target_height=2, lock_aspect=False, build_plane=BuildPlane.FLOOR, direction=Direction.EAST)
    art = convert_image(png_bytes([[(255, 0, 0, 255)] * 3, [(0, 255, 0, 255)] * 3]), settings)
    assert schematic_dimensions(art, settings) == (2, 1, 3)
    assert pixel_to_region(0, 0, art, settings) == (0, 0, 2)
    assert pixel_to_region(2, 1, art, settings) == (1, 0, 0)


def test_litematic_round_trip(tmp_path: Path) -> None:
    settings = ConvertSettings(name="round-trip", target_width=2, target_height=1, lock_aspect=False, palette_mode=PaletteMode.WOOL)
    art = convert_image(png_bytes([[(255, 255, 255, 255), (0, 0, 0, 255)]]), settings)
    output = tmp_path / "round-trip.litematic"
    create_litematic(art, settings, output)
    schematic = Schematic.load(str(output))
    region = list(schematic.regions.values())[0]
    assert region.width == 2
    assert region.height == 1
    assert region.length == 1
    assert region[0, 0, 0].id != "minecraft:air"
    assert region[1, 0, 0].id != "minecraft:air"
