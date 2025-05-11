from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request, Form, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import shutil
import os
from typing import List, Dict
import uuid
from sqlalchemy.orm import Session
import mimetypes
import time
import logging
import asyncio
from datetime import datetime, timedelta

from database import get_db, create_tables, Image

# 配置日志记录器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("picui")

# 创建文件处理器
file_handler = logging.FileHandler("upload.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# 获取环境变量
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")
API_TOKEN = os.getenv("API_TOKEN", "mysecrettoken")  # 默认token值

# 并发控制配置
MAX_CONCURRENT_UPLOADS = int(os.getenv("MAX_CONCURRENT_UPLOADS", 20))  # 最大并发上传数
# 创建信号量控制并发
upload_semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)

app = FastAPI(
    title="PicUI图床服务",
    description="一个简单高效的图片上传和管理服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "图片", "description": "图片上传、查看和管理操作"},
        {"name": "系统", "description": "系统相关接口"}
    ]
)

# 确保上传目录存在
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 允许的图片格式
ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp", 
    "bmp", "tiff", "tif", "svg", "ico", 
    "heic", "heif", "avif", "jfif", "pjpeg", "pjp"
}

# 文件大小限制 (修改为15MB)
MAX_SIZE = int(os.getenv("MAX_FILE_SIZE", 15 * 1024 * 1024))  # 默认15MB

# 频率限制配置
RATE_LIMIT = int(os.getenv("RATE_LIMIT", 20))  # 每分钟最大请求数
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))  # 时间窗口（秒）

# 存储IP请求次数的字典
ip_request_counters: Dict[str, Dict] = {}

# 在应用启动时创建数据库表
@app.on_event("startup")
def startup_event():
    create_tables()

# 检查文件格式是否允许
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 频率限制中间件
def rate_limit(request: Request):
    client_ip = request.client.host
    current_time = datetime.now()
    
    # 初始化或获取IP的请求计数器
    if client_ip not in ip_request_counters:
        ip_request_counters[client_ip] = {
            "count": 0,
            "reset_time": current_time + timedelta(seconds=RATE_LIMIT_WINDOW)
        }
    
    # 检查是否需要重置计数器
    if current_time >= ip_request_counters[client_ip]["reset_time"]:
        ip_request_counters[client_ip] = {
            "count": 0,
            "reset_time": current_time + timedelta(seconds=RATE_LIMIT_WINDOW)
        }
    
    # 增加请求计数
    ip_request_counters[client_ip]["count"] += 1
    
    # 检查是否超过限制
    if ip_request_counters[client_ip]["count"] > RATE_LIMIT:
        reset_time = ip_request_counters[client_ip]["reset_time"]
        retry_after = int((reset_time - current_time).total_seconds())
        
        # 清理过期的IP记录（可选，防止内存泄漏）
        clean_expired_records()
        
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后再试",
            headers={"Retry-After": str(retry_after)}
        )
    
    return True

# 清理过期的IP记录
def clean_expired_records():
    current_time = datetime.now()
    expired_ips = []
    
    for ip, data in ip_request_counters.items():
        if current_time >= data["reset_time"]:
            expired_ips.append(ip)
    
    for ip in expired_ips:
        del ip_request_counters[ip]

# 验证token的依赖函数
def verify_token(token: str = Form(...)):
    if token != API_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="无效的访问令牌"
        )
    return token

@app.post("/upload", tags=["图片"], summary="上传图片", description="上传图片文件并返回访问URL")
async def upload_image(
    file: UploadFile = File(..., description="要上传的图片文件"), 
    token: str = Form(..., description="访问令牌"),
    db: Session = Depends(get_db), 
    request: Request = None,
    _: bool = Depends(rate_limit),  # 添加频率限制依赖
    __: str = Depends(verify_token)  # 添加token验证依赖
):
    # 使用信号量控制并发
    async with upload_semaphore:
        # 检查文件类型
        if not allowed_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"不支持的图片格式: {file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else '未知格式'}。只允许上传以下格式: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        
        # 读取文件内容
        contents = await file.read()
        
        # 检查文件大小
        if len(contents) > MAX_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件过大: {len(contents)/1024/1024:.2f}MB。文件大小不能超过{MAX_SIZE/1024/1024:.0f}MB"
            )
        
        # 重置文件指针
        await file.seek(0)
        
        # 生成唯一文件名
        file_extension = file.filename.split('.')[-1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_location = os.path.join(UPLOAD_DIR, unique_filename)
        
        # 保存文件
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 获取文件大小（KB）
        file_size = os.path.getsize(file_location) / 1024
        
        # 获取MIME类型
        mime_type = mimetypes.guess_type(file_location)[0]
        if not mime_type:
            mime_type = f"image/{file_extension}"
        
        # 保存到数据库
        db_image = Image(
            filename=unique_filename,
            original_filename=file.filename,
            size=file_size,
            mime_type=mime_type
        )
        db.add(db_image)
        db.commit()
        db.refresh(db_image)
        
        # 动态生成URL
        if request:
            # 如果请求可用，从请求中构建URL
            host = request.headers.get("host", "localhost")
            scheme = request.headers.get("x-forwarded-proto", "http")
            base_url = f"{scheme}://{host}"
            file_url = f"{base_url}/images/{unique_filename}"
            
            # 记录上传信息到日志
            client_ip = request.client.host
            logger.info(f"{client_ip} 上传了 {file.filename}")
        else:
            # 如果不可用，使用配置的BASE_URL
            file_url = f"{BASE_URL}/images/{unique_filename}"
            
            # 记录上传信息到日志（无法获取IP时）
            logger.info(f"未知IP 上传了 {file.filename}")
        
        return {"url": file_url, "filename": unique_filename, "id": db_image.id}

@app.get("/images/{filename}", tags=["图片"], summary="获取图片", description="通过文件名获取图片")
async def get_image(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(file_path)

@app.get("/images", tags=["图片"], summary="获取图片列表", description="获取所有上传的图片列表")
def list_images(db: Session = Depends(get_db), skip: int = 0, limit: int = 100):
    images = db.query(Image).offset(skip).limit(limit).all()
    return images

# 获取支持的图片格式
@app.get("/supported-formats", tags=["系统"], summary="获取支持的图片格式", description="获取系统支持的图片格式和大小限制")
def get_supported_formats():
    return {"formats": sorted(list(ALLOWED_EXTENSIONS)), "max_size_mb": MAX_SIZE/1024/1024}

# 根路径重定向到前端页面
@app.get("/", tags=["系统"], summary="主页", description="访问图床服务主页")
async def root():
    return FileResponse("static/index.html")

# 添加健康检查端点
@app.get("/health", tags=["系统"], summary="健康检查", description="检查服务是否正常运行")
async def health_check():
    return {"status": "healthy"}

# 添加频率限制状态端点（仅供管理员使用）
@app.get("/rate-limit-status", tags=["系统"], summary="频率限制状态", description="获取当前频率限制状态（仅供管理员使用）")
async def rate_limit_status():
    current_time = datetime.now()
    status_data = {}
    
    for ip, data in ip_request_counters.items():
        remaining_time = (data["reset_time"] - current_time).total_seconds()
        if remaining_time > 0:
            status_data[ip] = {
                "count": data["count"],
                "remaining_requests": max(0, RATE_LIMIT - data["count"]),
                "reset_in_seconds": int(remaining_time)
            }
    
    return {
        "rate_limit": RATE_LIMIT,
        "window_seconds": RATE_LIMIT_WINDOW,
        "active_ips": len(status_data),
        "ip_data": status_data
    }

# 添加并发状态端点（仅供管理员使用）
@app.get("/concurrency-status", tags=["系统"], summary="并发状态", description="获取当前并发上传状态（仅供管理员使用）")
async def concurrency_status(token: str = None):
    # 简单的token验证
    if token != API_TOKEN:
        raise HTTPException(status_code=403, detail="无效的访问令牌")
    
    return {
        "max_concurrent_uploads": MAX_CONCURRENT_UPLOADS,
        "current_active_uploads": MAX_CONCURRENT_UPLOADS - upload_semaphore._value,
        "available_slots": upload_semaphore._value
    }

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 挂载上传目录
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True) 