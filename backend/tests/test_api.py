from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models import ConvertSettings, PaletteMode


def sample_png() -> bytes:
    image = Image.new("RGBA", (2, 2), (255, 255, 255, 255))
    image.putpixel((1, 1), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_convert_and_downloads() -> None:
    client = TestClient(app)
    settings = ConvertSettings(target_width=2, target_height=2, lock_aspect=False, palette_mode=PaletteMode.WOOL)
    response = client.post(
        "/api/convert",
        files={"file": ("tiny.png", sample_png(), "image/png")},
        data={"settings": settings.model_dump_json()},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["width"] == 2
    assert payload["height"] == 2
    assert payload["block_count"] == 3
    assert payload["air_count"] == 1

    litematic = client.get(payload["downloads"]["litematic"])
    assert litematic.status_code == 200
    assert len(litematic.content) > 100

    materials = client.get(payload["downloads"]["materials_json"])
    assert materials.status_code == 200
    assert json.loads(materials.text)[0]["count"] >= 1
