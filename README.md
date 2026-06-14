# MC Pixel Litematic Python

![License: GPL-3.0-only](https://img.shields.io/badge/license-GPL--3.0--only-blue)
![Backend](https://img.shields.io/badge/backend-FastAPI-009688)
![Image](https://img.shields.io/badge/image-Pillow%20%2B%20NumPy-3776AB)
![Litematic](https://img.shields.io/badge/export-.litematic-44AA44)

Python/FastAPI 版 Minecraft 图片转 `.litematic` 工具。前端负责上传、设置和预览，后端使用 Pillow、NumPy 和 litemapy 生成 Litematica 投影文件。

这个仓库适合本地使用、自托管、二次开发和研究 `.litematic` 生成流程。如果你只想部署到 Cloudflare Pages，请使用纯 JS 仓库 `mc-pixel-litematic-cloudflare`。

## 功能亮点

- 图片导入：支持 PNG、JPG、WebP、GIF 首帧。
- 像素画模式：普通墙画、地画、天花板投影。
- Map Art 模式：支持 128x128 单地图和多地图拼接。
- 方块筛选：全部、羊毛、混凝土、陶瓦、地图画可用、生存友好、自定义方块。
- 颜色匹配：快速 RGB、标准 LAB、高质量 LAB + Floyd-Steinberg 抖动。
- 结构方向：north、south、east、west。
- 后端导出：`.litematic`、材料清单 CSV/JSON、预览 PNG。
- 测试覆盖：颜色转换、透明像素、坐标映射、API 上传、`.litematic` 读回校验。

## 快速开始

### 1. 启动后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
```

后端健康检查：

```text
http://127.0.0.1:8787/api/health
```

### 2. 启动前端

打开另一个 PowerShell：

```powershell
cd frontend
npm install
npm run dev
```

打开：

```text
http://127.0.0.1:5173
```

## 测试

后端测试：

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q
```

前端构建：

```powershell
cd frontend
npm run build
```

推荐发布前跑：

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q

cd ..\frontend
npm run build
npm audit --audit-level=high
```

## API

### `GET /api/health`

返回后端状态。

### `GET /api/blocks`

返回可选方块、颜色、分类、版本和生存/地图画标记。

### `POST /api/convert`

表单参数：

- `file`: 图片文件。
- `settings`: JSON 字符串，包含尺寸、模式、方块筛选、朝向、质量等设置。

返回：

- 预览 PNG data URL。
- 材料清单。
- `.litematic`、CSV、JSON、PNG 下载地址。

### `GET /api/download/{result_id}/{kind}`

下载生成结果。`kind` 支持：

- `litematic`
- `preview.png`
- `materials.csv`
- `materials.json`

## 项目结构

```text
.
├─ backend/
│  ├─ app/
│  │  ├─ data/blocks.py       # 方块颜色表
│  │  ├─ image_convert.py     # 图片缩放、匹配、抖动、预览
│  │  ├─ litematic_export.py  # litemapy 导出和坐标映射
│  │  ├─ main.py              # FastAPI 路由
│  │  ├─ models.py            # API/settings 数据模型
│  │  └─ palette.py           # 方块筛选
│  ├─ tests/
│  └─ requirements.txt
└─ frontend/
   ├─ src/
   │  ├─ main.tsx             # React UI
   │  ├─ styles.css
   │  └─ types.ts
   └─ package.json
```

## 给 AI Agent 的快速上下文

这是 Python 服务版，不是 Cloudflare 静态版。不要把浏览器端 `.litematic` writer 加回这个仓库；这个仓库的生成逻辑应保留在 FastAPI 后端。

重要入口：

- API：`backend/app/main.py`
- 图片转换：`backend/app/image_convert.py`
- `.litematic` 导出：`backend/app/litematic_export.py`
- 数据模型：`backend/app/models.py`
- 前端 UI：`frontend/src/main.tsx`

验证命令：

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q

cd ..\frontend
npm run build
```

## Python 版和 Cloudflare 版怎么选？

| 版本 | 仓库 | 适合场景 | 后端 |
| --- | --- | --- | --- |
| Cloudflare 纯 JS 版 | `mc-pixel-litematic-cloudflare` | 静态部署、公开网站、无服务器 | 不需要 |
| Python 版 | `mc-pixel-litematic-python` | 本地使用、自托管、研究和扩展 | FastAPI |

## License

GPL-3.0-only. See [LICENSE](LICENSE).

This edition depends on `litemapy`, so the repository is licensed under GPL-3.0-only for compatibility.

## Disclaimer

This project is not affiliated with Mojang, Microsoft, Minecraft, Litematica, or litemapy.
