from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ArtMode(str, Enum):
    PIXEL = "pixel"
    MAP = "map"


class BuildPlane(str, Enum):
    WALL = "wall"
    FLOOR = "floor"
    CEILING = "ceiling"


class Direction(str, Enum):
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class FitMode(str, Enum):
    STRETCH = "stretch"
    CONTAIN = "contain"
    COVER = "cover"


class QualityMode(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    HIGH = "high"


class TransparentMode(str, Enum):
    AIR = "air"
    WHITE = "white"
    BLACK = "black"


class PaletteMode(str, Enum):
    ALL = "all"
    WOOL = "wool"
    CONCRETE = "concrete"
    TERRACOTTA = "terracotta"
    PIXEL_ART = "pixel_art"
    MAP_ART = "map_art"
    SURVIVAL = "survival"
    CUSTOM = "custom"


class MapVariant(str, Enum):
    FLAT = "flat"
    STAIRS = "stairs"


class MapPreviewMode(str, Enum):
    MAP = "map"
    BLOCKS = "blocks"


class ConvertSettings(BaseModel):
    name: str = Field(default="pixel-art", max_length=80)
    author: str = Field(default="MC Pixel Litematic Studio", max_length=80)
    mc_version: Literal["1.20.1", "1.21"] = "1.21"
    art_mode: ArtMode = ArtMode.PIXEL
    target_width: int = Field(default=64, ge=1, le=1024)
    target_height: int = Field(default=64, ge=1, le=1024)
    lock_aspect: bool = True
    fit_mode: FitMode = FitMode.CONTAIN
    quality: QualityMode = QualityMode.STANDARD
    transparent_mode: TransparentMode = TransparentMode.AIR
    palette_mode: PaletteMode = PaletteMode.ALL
    palette_modes: list[PaletteMode] = Field(default_factory=lambda: [PaletteMode.ALL])
    custom_blocks: list[str] = Field(default_factory=list)
    replacements: dict[str, str] = Field(default_factory=dict)
    build_plane: BuildPlane = BuildPlane.WALL
    direction: Direction = Direction.NORTH
    map_columns: int = Field(default=1, ge=1, le=8)
    map_rows: int = Field(default=1, ge=1, le=8)
    map_variant: MapVariant = MapVariant.FLAT
    map_preview: MapPreviewMode = MapPreviewMode.MAP
    show_grid: bool = True


class BlockInfo(BaseModel):
    id: str
    name: str
    rgb: tuple[int, int, int]
    categories: list[str]
    versions: list[str]
    map_art: bool
    survival: bool


class MaterialItem(BaseModel):
    id: str
    name: str
    count: int
    rgb: tuple[int, int, int]


class ConvertResponse(BaseModel):
    result_id: str
    width: int
    height: int
    depth: int
    block_count: int
    air_count: int
    preview_png: str
    block_preview_png: str | None = None
    map_preview_png: str | None = None
    materials: list[MaterialItem]
    downloads: dict[str, str]
