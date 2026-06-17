from __future__ import annotations

from app.data.blocks import BLOCKS, BlockColor, by_id
from app.models import ConvertSettings, PaletteMode

PIXEL_ART_BLOCKS = {
    "minecraft:white_wool",
    "minecraft:white_concrete",
    "minecraft:white_terracotta",
    "minecraft:light_gray_wool",
    "minecraft:pink_wool",
    "minecraft:pink_concrete",
    "minecraft:light_blue_wool",
    "minecraft:cyan_wool",
    "minecraft:lime_wool",
    "minecraft:lime_concrete",
    "minecraft:lime_terracotta",
    "minecraft:quartz_block",
    "minecraft:calcite",
    "minecraft:bone_block",
    "minecraft:mushroom_stem",
    "minecraft:end_stone",
    "minecraft:smooth_sandstone",
    "minecraft:snow_block",
    "minecraft:sea_lantern",
    "minecraft:verdant_froglight",
    "minecraft:pearlescent_froglight",
    "minecraft:ochre_froglight",
    "minecraft:prismarine",
    "minecraft:cherry_planks",
}


def select_blocks(settings: ConvertSettings) -> list[BlockColor]:
    blocks = [block for block in BLOCKS if settings.mc_version in block.versions]
    modes = settings.palette_modes or [settings.palette_mode]

    if PaletteMode.CUSTOM in modes:
        index = by_id()
        selected = [index[block_id] for block_id in settings.custom_blocks if block_id in index]
        return [block for block in selected if settings.mc_version in block.versions] or blocks

    if PaletteMode.ALL in modes:
        return blocks

    return [block for block in blocks if block_matches_palette(block, modes)]


def block_matches_palette(block: BlockColor, modes: list[PaletteMode]) -> bool:
    for mode in modes:
        if mode == PaletteMode.ALL:
            return True
        if mode == PaletteMode.PIXEL_ART and block.id in PIXEL_ART_BLOCKS:
            return True
        if mode == PaletteMode.MAP_ART and block.map_art:
            return True
        if mode == PaletteMode.SURVIVAL and block.survival:
            return True
        if mode not in (PaletteMode.CUSTOM, PaletteMode.MAP_ART, PaletteMode.SURVIVAL) and mode.value in block.categories:
            return True
    return False
