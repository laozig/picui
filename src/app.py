from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response
import logging
import threading
import os
import prometheus_client
from prometheus_client import CollectorRegistry
import uuid

from src.database import create_tables, get_db, Image, UploadLog, ShortLink
from src.routes import router as api_router
from src.page_routes import router as page_router, set_templates
from src.utils import check_disk_usage
from src.session import clean_expired_sessions

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
SESSION_CLEANUP_INTERVAL = int(os.getenv("SESSION_CLEANUP_INTERVAL", 3600))  # 默认每小时清理一次会话

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

# 定期清理过期会话
def schedule_session_cleanup():
    """定期清理过期会话"""
    clean_expired_sessions()
    # 计划下一次清理
    threading.Timer(SESSION_CLEANUP_INTERVAL, schedule_session_cleanup).start()

# 在应用启动时创建数据库表
@app.on_event("startup")
def startup_event():
    """应用启动时执行的初始化操作"""
    create_tables()
    
    # 更新现有数据的user_id字段
    try:
        # 获取数据库连接
        db = next(get_db())
        
        # 检查是否有需要设置user_id的数据
        images_without_user_id = db.query(Image).filter(Image.user_id == None).all()
        logs_without_user_id = db.query(UploadLog).filter(UploadLog.user_id == None).all()
        links_without_user_id = db.query(ShortLink).filter(ShortLink.user_id == None).all()
        
        # 按IP地址分组
        ip_groups = {}
        
        # 处理图片数据
        for img in images_without_user_id:
            if img.upload_ip not in ip_groups:
                ip_groups[img.upload_ip] = str(uuid.uuid4())
            img.user_id = ip_groups[img.upload_ip]
        
        # 处理日志数据
        for log in logs_without_user_id:
            if log.ip_address not in ip_groups:
                ip_groups[log.ip_address] = str(uuid.uuid4())
            log.user_id = ip_groups[log.ip_address]
        
        # 处理短链接数据（根据关联的图片）
        for link in links_without_user_id:
            img = db.query(Image).filter(Image.filename == link.target_file).first()
            if img and img.user_id:
                link.user_id = img.user_id
            elif img and img.upload_ip in ip_groups:
                link.user_id = ip_groups[img.upload_ip]
        
        # 提交更改
        db.commit()
        logger.info(f"✓ 数据库迁移完成: 更新了 {len(images_without_user_id)} 个图片, {len(logs_without_user_id)} 个日志, {len(links_without_user_id)} 个短链接的用户ID")
        
    except Exception as e:
        logger.error(f"数据库迁移失败: {str(e)}", exc_info=True)
    
    # 启动磁盘空间检查
    schedule_disk_check()
    # 启动会话清理
    schedule_session_cleanup()
    logger.info("✓ 应用启动完成，会话系统已启用")

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