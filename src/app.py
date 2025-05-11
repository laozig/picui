from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response
import logging
import threading
import os
import prometheus_client
from prometheus_client import CollectorRegistry

from src.database import create_tables
from src.routes import router as api_router
from src.page_routes import router as page_router, set_templates
from src.utils import check_disk_usage

# 配置日志记录器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("picui")

# 创建文件处理器
file_handler = logging.FileHandler("upload.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# 环境变量
DISK_CHECK_INTERVAL = int(os.getenv("DISK_CHECK_INTERVAL", 3600))  # 默认每小时检查一次
DISK_USAGE_THRESHOLD = float(os.getenv("DISK_USAGE_THRESHOLD", 80.0))  # 默认阈值80%
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")

# 设置Prometheus指标
try:
    # 创建自定义注册表
    REGISTRY = CollectorRegistry()
    
    # 启用Prometheus监控
    PROMETHEUS_ENABLED = True
except Exception as e:
    print(f"Prometheus初始化失败: {str(e)}")
    PROMETHEUS_ENABLED = False
    REGISTRY = None

# 创建FastAPI应用
app = FastAPI(
    title="PicUI图床服务",
    description="一个简单高效的图片上传和管理服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "图片", "description": "图片上传、查看和管理操作"},
        {"name": "系统", "description": "系统相关接口"},
        {"name": "短链接", "description": "短链接生成和管理"},
        {"name": "页面", "description": "Web页面路由"}
    ]
)

# 配置模板目录
templates = Jinja2Templates(directory="templates")
set_templates(templates)

# 确保上传目录存在
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 定期检查磁盘空间
def schedule_disk_check():
    """定期检查磁盘空间利用率"""
    check_disk_usage(UPLOAD_DIR, DISK_USAGE_THRESHOLD)
    # 计划下一次检查
    threading.Timer(DISK_CHECK_INTERVAL, schedule_disk_check).start()

# 在应用启动时创建数据库表
@app.on_event("startup")
def startup_event():
    """应用启动时执行的初始化操作"""
    create_tables()
    # 启动磁盘空间检查
    schedule_disk_check()

# Prometheus 指标接口
@app.get("/metrics")
async def metrics():
    """返回Prometheus指标"""
    if PROMETHEUS_ENABLED and REGISTRY:
        metrics_text = prometheus_client.generate_latest(REGISTRY).decode("utf-8")
        return Response(content=metrics_text, media_type="text/plain")
    return Response(content="Prometheus监控未启用", media_type="text/plain")

# 包含API路由
app.include_router(api_router)

# 包含页面路由
app.include_router(page_router)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 挂载上传目录
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads") 