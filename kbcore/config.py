"""全局路径与常量。所有路径都基于项目根目录推导，可整包移动。"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

KB_DIR = BASE_DIR / "kb"          # 知识库正文：文件原样存放在这里
WEB_DIR = BASE_DIR / "web"        # 前端静态资源
DATA_DIR = BASE_DIR / "data"      # 索引库、运行时文件
DB_PATH = DATA_DIR / "kb.sqlite3"

DEFAULT_PORT = 8777
PORT_SCAN = 20                      # 端口被占用时向上顺延的次数

MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # 单次请求体上限
CHUNK_SIZE = 1100                   # 检索切片目标长度（字符）
CHUNK_HARD_LIMIT = 1800             # 单片硬上限
DOC_PREVIEW_LIMIT = 400_000         # 单文档返回给前端的最大字符数

# 知识库根目录下不参与索引的目录 / 文件
IGNORED_DIRS = {".git", ".obsidian", ".trash", "__pycache__", "node_modules"}
IGNORED_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}

for _d in (KB_DIR, DATA_DIR, WEB_DIR):
    _d.mkdir(parents=True, exist_ok=True)
