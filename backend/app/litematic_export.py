from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile

from litemapy import BlockState, Region

from app.image_convert import AIR_ID, ConvertedArt
from app.models import BuildPlane, ConvertSettings, Direction


def schematic_dimensions(art: ConvertedArt, settings: ConvertSettings) -> tuple[int, int, int]:
    image_w, image_h = art.width, art.height
    if settings.art_mode.value == "map":
        if settings.direction in (Direction.EAST, Direction.WEST):
            return image_h, art.depth, image_w
        return image_w, art.depth, image_h
    if settings.build_plane == BuildPlane.WALL:
        if settings.direction in (Direction.NORTH, Direction.SOUTH):
            return image_w, image_h, 1
        return 1, image_h, image_w
    if settings.direction in (Direction.EAST, Direction.WEST):
        return image_h, art.depth, image_w
    return image_w, art.depth, image_h


def pixel_to_region(x: int, y: int, art: ConvertedArt, settings: ConvertSettings) -> tuple[int, int, int]:
    return pixel_to_region_level(x, y, art.height_grid[y][x], art, settings)


def pixel_to_region_level(x: int, y: int, level: int, art: ConvertedArt, settings: ConvertSettings) -> tuple[int, int, int]:
    w, h = art.width, art.height
    if settings.art_mode.value == "map":
        if settings.direction == Direction.NORTH:
            return x, level, y
        if settings.direction == Direction.SOUTH:
            return w - 1 - x, level, h - 1 - y
        if settings.direction == Direction.EAST:
            return y, level, w - 1 - x
        return h - 1 - y, level, x

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
    block_states = {AIR_ID: block_state_from_id(AIR_ID)}

    placements = art.placements or [
        {"x": x, "y": y, "level": art.height_grid[y][x], "block_id": block_id}
        for y, row in enumerate(art.block_grid)
        for x, block_id in enumerate(row)
    ]
    for placement in placements:
        block_id = placement["block_id"]
        if block_id == AIR_ID:
            continue
        if block_id not in block_states:
            block_states[block_id] = block_state_from_id(block_id)
        rx, ry, rz = pixel_to_region_level(placement["x"], placement["y"], placement["level"], art, settings)
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


def block_state_from_id(block_id: str) -> BlockState:
    if "[" not in block_id:
        return BlockState(block_id)
    name, raw_props = block_id.rstrip("]").split("[", 1)
    props = {}
    for entry in raw_props.split(","):
        key, value = entry.split("=", 1)
        props[key.strip()] = value.strip()
    return BlockState(name, **props)
