# MC Pixel Litematic Python

Python/FastAPI 版 Minecraft 图片转 `.litematic` 工具。前端负责上传和预览，后端使用 Pillow、NumPy、litemapy 生成投影文件。

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q
```

## License

GPL-3.0-only. See `LICENSE`.

This edition depends on `litemapy`, so the repository is licensed under GPL-3.0-only for compatibility.
