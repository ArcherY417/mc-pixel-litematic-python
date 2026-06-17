from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.data.blocks import BlockColor
from app.models import MapVariant


MapShade = Literal[0, 1, 2]


@dataclass(frozen=True)
class MapColorCandidate:
    block_id: str
    base_block_id: str
    map_rgb: tuple[int, int, int]
    block_rgb: tuple[int, int, int]
    shade: MapShade
    is_water: bool = False
    water_depth: int = 0


SHADE_MULTIPLIERS: dict[MapShade, int] = {0: 180, 1: 220, 2: 255}
WATER_DEPTH: dict[MapShade, int] = {0: 10, 1: 5, 2: 1}
WATER_BASE = (64, 64, 255)

MAP_BASES: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("minecraft:grass_block", (127, 178, 56)),
    ("minecraft:smooth_sandstone", (247, 233, 163)),
    ("minecraft:mushroom_stem", (199, 199, 199)),
    ("minecraft:red_concrete", (255, 0, 0)),
    ("minecraft:ice", (160, 160, 255)),
    ("minecraft:iron_block", (167, 167, 167)),
    ("minecraft:oak_planks", (143, 119, 72)),
    ("minecraft:white_wool", (255, 255, 255)),
    ("minecraft:orange_wool", (216, 127, 51)),
    ("minecraft:magenta_wool", (178, 76, 216)),
    ("minecraft:light_blue_wool", (102, 153, 216)),
    ("minecraft:yellow_wool", (229, 229, 51)),
    ("minecraft:lime_wool", (127, 204, 25)),
    ("minecraft:pink_wool", (242, 127, 165)),
    ("minecraft:gray_wool", (76, 76, 76)),
    ("minecraft:light_gray_wool", (153, 153, 153)),
    ("minecraft:cyan_wool", (76, 127, 153)),
    ("minecraft:purple_wool", (127, 63, 178)),
    ("minecraft:blue_wool", (51, 76, 178)),
    ("minecraft:brown_wool", (102, 76, 51)),
    ("minecraft:green_wool", (102, 127, 51)),
    ("minecraft:red_wool", (153, 51, 51)),
    ("minecraft:black_wool", (25, 25, 25)),
    ("minecraft:gold_block", (250, 238, 77)),
    ("minecraft:diamond_block", (92, 219, 213)),
    ("minecraft:lapis_block", (74, 128, 255)),
    ("minecraft:emerald_block", (0, 217, 58)),
    ("minecraft:podzol", (129, 86, 49)),
    ("minecraft:netherrack", (112, 2, 0)),
    ("minecraft:snow_block", (255, 252, 245)),
    ("minecraft:white_terracotta", (209, 177, 161)),
    ("minecraft:orange_terracotta", (159, 82, 36)),
    ("minecraft:magenta_terracotta", (149, 87, 108)),
    ("minecraft:light_blue_terracotta", (112, 108, 138)),
    ("minecraft:yellow_terracotta", (186, 133, 36)),
    ("minecraft:lime_terracotta", (103, 117, 53)),
    ("minecraft:pink_terracotta", (160, 77, 78)),
    ("minecraft:gray_terracotta", (57, 41, 35)),
    ("minecraft:light_gray_terracotta", (135, 107, 98)),
    ("minecraft:cyan_terracotta", (87, 92, 92)),
    ("minecraft:purple_terracotta", (122, 73, 88)),
    ("minecraft:blue_terracotta", (76, 62, 92)),
    ("minecraft:brown_terracotta", (76, 50, 35)),
    ("minecraft:green_terracotta", (76, 82, 42)),
    ("minecraft:red_terracotta", (142, 60, 46)),
    ("minecraft:black_terracotta", (37, 22, 16)),
    ("minecraft:quartz_block", (255, 250, 250)),
    ("minecraft:prismarine", (99, 156, 151)),
    ("minecraft:warped_wart_block", (22, 126, 134)),
    ("minecraft:deepslate", (100, 100, 100)),
)

MAP_ART_BLOCK_IDS = {block_id for block_id, _ in MAP_BASES} | {"minecraft:water"}


def create_map_palette(blocks: list[BlockColor], variant: MapVariant) -> list[MapColorCandidate]:
    by_id = {block.id: block for block in blocks}
    shades: tuple[MapShade, ...] = (0, 1, 2) if variant == MapVariant.STAIRS else (1,)
    candidates: list[MapColorCandidate] = []
    for block_id, base_rgb in MAP_BASES:
        block = by_id.get(block_id)
        if not block:
            continue
        for shade in shades:
            candidates.append(
                MapColorCandidate(
                    block_id=block_id,
                    base_block_id=block_id,
                    map_rgb=shade_rgb(base_rgb, shade),
                    block_rgb=block.rgb,
                    shade=shade,
                )
            )
    if "minecraft:water" in by_id:
        for shade in shades:
            candidates.append(
                MapColorCandidate(
                    block_id="minecraft:water[level=0]",
                    base_block_id="minecraft:water",
                    map_rgb=shade_rgb(WATER_BASE, shade),
                    block_rgb=WATER_BASE,
                    shade=shade,
                    is_water=True,
                    water_depth=WATER_DEPTH[shade],
                )
            )
    return candidates


def shade_rgb(rgb: tuple[int, int, int], shade: MapShade) -> tuple[int, int, int]:
    multiplier = SHADE_MULTIPLIERS[shade]
    return tuple((channel * multiplier) // 255 for channel in rgb)
