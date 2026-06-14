from __future__ import annotations

from app.data.blocks import BLOCKS, BlockColor, by_id
from app.models import ConvertSettings, PaletteMode


def select_blocks(settings: ConvertSettings) -> list[BlockColor]:
    blocks = [block for block in BLOCKS if settings.mc_version in block.versions]

    if settings.palette_mode == PaletteMode.CUSTOM:
        index = by_id()
        selected = [index[block_id] for block_id in settings.custom_blocks if block_id in index]
        return [block for block in selected if settings.mc_version in block.versions] or blocks

    if settings.palette_mode == PaletteMode.ALL:
        return blocks

    if settings.palette_mode == PaletteMode.MAP_ART:
        return [block for block in blocks if block.map_art]

    if settings.palette_mode == PaletteMode.SURVIVAL:
        return [block for block in blocks if block.survival]

    category = settings.palette_mode.value
    return [block for block in blocks if category in block.categories]
