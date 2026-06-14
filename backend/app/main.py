from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.data.blocks import BLOCKS, by_id
from app.image_convert import ConvertedArt, convert_image, data_url_png
from app.litematic_export import litematic_bytes, material_csv
from app.models import BlockInfo, ConvertResponse, ConvertSettings, MaterialItem


@dataclass
class StoredResult:
    settings: ConvertSettings
    art: ConvertedArt
    litematic: bytes


RESULTS: dict[str, StoredResult] = {}

app = FastAPI(title="MC Pixel Litematic Studio", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/blocks", response_model=list[BlockInfo])
def blocks() -> list[BlockInfo]:
    return [
        BlockInfo(
            id=block.id,
            name=block.name,
            rgb=block.rgb,
            categories=list(block.categories),
            versions=list(block.versions),
            map_art=block.map_art,
            survival=block.survival,
        )
        for block in BLOCKS
    ]


@app.post("/api/convert", response_model=ConvertResponse)
async def convert(file: UploadFile = File(...), settings: str = Form(...)) -> ConvertResponse:
    try:
        parsed_settings = ConvertSettings.model_validate_json(settings)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid settings: {exc}") from exc

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="No image was uploaded.")

    try:
        art = convert_image(image_bytes, parsed_settings)
        litematic = litematic_bytes(art, parsed_settings)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result_id = uuid.uuid4().hex
    RESULTS[result_id] = StoredResult(parsed_settings, art, litematic)
    return build_response(result_id, RESULTS[result_id])


@app.get("/api/download/{result_id}/{kind}")
def download(result_id: str, kind: str) -> Response:
    stored = RESULTS.get(result_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Result not found.")
    safe_name = safe_filename(stored.settings.name or "pixel-art")

    if kind == "litematic":
        return Response(
            stored.litematic,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.litematic"'},
        )
    if kind == "preview.png":
        return Response(
            stored.art.preview_png,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}-preview.png"'},
        )
    if kind == "materials.csv":
        return Response(
            material_csv(stored.art.materials),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}-materials.csv"'},
        )
    if kind == "materials.json":
        payload = [
            {"block_id": block_id, "count": count}
            for block_id, count in stored.art.materials.most_common()
        ]
        return Response(
            json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}-materials.json"'},
        )
    raise HTTPException(status_code=404, detail="Unknown download type.")


def build_response(result_id: str, stored: StoredResult) -> ConvertResponse:
    block_index = by_id()
    width, height, depth = stored.art.width, stored.art.height, stored.art.depth
    materials = [
        MaterialItem(
            id=block_id,
            name=block_index[block_id].name,
            count=count,
            rgb=block_index[block_id].rgb,
        )
        for block_id, count in stored.art.materials.most_common()
        if block_id in block_index
    ]
    return ConvertResponse(
        result_id=result_id,
        width=width,
        height=height,
        depth=depth,
        block_count=sum(stored.art.materials.values()),
        air_count=stored.art.air_count,
        preview_png=data_url_png(stored.art.preview_png),
        materials=materials,
        downloads={
            "litematic": f"/api/download/{result_id}/litematic",
            "preview_png": f"/api/download/{result_id}/preview.png",
            "materials_csv": f"/api/download/{result_id}/materials.csv",
            "materials_json": f"/api/download/{result_id}/materials.json",
        },
    )


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")
    return cleaned or "pixel-art"
