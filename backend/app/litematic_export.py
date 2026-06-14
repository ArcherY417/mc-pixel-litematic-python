from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

from litemapy import BlockState, Region

from app.image_convert import AIR_ID, ConvertedArt
from app.models import BuildPlane, ConvertSettings, Direction


def schematic_dimensions(art: ConvertedArt, settings: ConvertSettings) -> tuple[int, int, int]:
    image_w, image_h = art.width, art.height
    if settings.build_plane == BuildPlane.WALL:
        if settings.direction in (Direction.NORTH, Direction.SOUTH):
            return image_w, image_h, 1
        return 1, image_h, image_w
    if settings.direction in (Direction.EAST, Direction.WEST):
        return image_h, art.depth, image_w
    return image_w, art.depth, image_h


def pixel_to_region(x: int, y: int, art: ConvertedArt, settings: ConvertSettings) -> tuple[int, int, int]:
    w, h = art.width, art.height
    level = art.height_grid[y][x]

    if settings.build_plane == BuildPlane.WALL:
        ry = h - 1 - y
        if settings.direction == Direction.NORTH:
            return x, ry, 0
        if settings.direction == Direction.SOUTH:
            return w - 1 - x, ry, 0
        if settings.direction == Direction.EAST:
            return 0, ry, x
        return 0, ry, w - 1 - x

    ry = level if settings.build_plane == BuildPlane.FLOOR else art.depth - 1 - level
    if settings.direction == Direction.NORTH:
        return x, ry, y
    if settings.direction == Direction.SOUTH:
        return w - 1 - x, ry, h - 1 - y
    if settings.direction == Direction.EAST:
        return y, ry, w - 1 - x
    return h - 1 - y, ry, x


def create_litematic(art: ConvertedArt, settings: ConvertSettings, output_path: Path) -> None:
    width, height, length = schematic_dimensions(art, settings)
    region = Region(0, 0, 0, width, height, length)
    block_states = {AIR_ID: BlockState(AIR_ID)}

    for y, row in enumerate(art.block_grid):
        for x, block_id in enumerate(row):
            if block_id == AIR_ID:
                continue
            if block_id not in block_states:
                block_states[block_id] = BlockState(block_id)
            rx, ry, rz = pixel_to_region(x, y, art, settings)
            region[rx, ry, rz] = block_states[block_id]

    schematic = region.as_schematic(
        name=settings.name or "pixel-art",
        author=settings.author or "MC Pixel Litematic Studio",
        description=(
            f"Generated from an image. Mode={settings.art_mode.value}, "
            f"plane={settings.build_plane.value}, direction={settings.direction.value}."
        ),
    )
    schematic.save(str(output_path))


def litematic_bytes(art: ConvertedArt, settings: ConvertSettings) -> bytes:
    with NamedTemporaryFile(suffix=".litematic", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        create_litematic(art, settings, tmp_path)
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def material_csv(materials: Counter[str]) -> str:
    lines = ["block_id,count"]
    for block_id, count in materials.most_common():
        lines.append(f"{block_id},{count}")
    return "\n".join(lines) + "\n"
