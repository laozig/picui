from fastapi import APIRouter, Depends, HTTPException, Request, Query, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from datetime import datetime, timedelta
import os
import uuid
import io
import time
import shutil
import asyncio
import logging
import threading
import concurrent.futures
from pathlib import Path
from typing import Optional, Dict, List, Union

from src.database import get_db, Image, UploadLog, ShortLink
from src.utils import (
    allowed_file, optimize_image, offline_image_check, 
    add_watermark, check_disk_usage, ALLOWED_EXTENSIONS
)

# 配置日志
logger = logging.getLogger("picui")

# 创建路由器
router = APIRouter()

# 全局变量
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_SIZE = int(os.getenv("MAX_FILE_SIZE", 15 * 1024 * 1024))  # 默认15MB
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
OFFLINE_CHECK_ENABLED = os.getenv("OFFLINE_CHECK_ENABLED", "false").lower() == "true"
SKIN_THRESHOLD = float(os.getenv("SKIN_THRESHOLD", "0.5"))
MAX_CONCURRENT_UPLOADS = int(os.getenv("MAX_CONCURRENT_UPLOADS", 20))
upload_semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)

# 创建线程池执行器，用于处理CPU密集型任务
thread_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=int(os.getenv("THREAD_POOL_SIZE", min(32, os.cpu_count() * 4))),
    thread_name_prefix="picui_worker"
)

# 请求计数器记录和频率限制
RATE_LIMIT = int(os.getenv("RATE_LIMIT", 20))  # 每分钟最大请求数
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))  # 时间窗口（秒）
request_counters = {}
request_counter_lock = threading.Lock()  # 添加线程锁确保计数器更新的原子性

# 清理过期的请求计数记录
def clean_old_request_data():
    """清理过期的请求计数记录"""
    current_time = time.time()
    
    with request_counter_lock:
        expired_keys = [key for key, data in request_counters.items() 
                      if current_time - data["last_reset"] > RATE_LIMIT_WINDOW]
        
        for key in expired_keys:
            del request_counters[key]

# 检查请求频率是否超限
def check_rate_limit(ip, current_time):
    """
    检查IP请求频率是否超限
    
    返回True表示未超限，False表示已超限
    """
    with request_counter_lock:
        # 如果IP不在计数器中，添加它
        if ip not in request_counters:
            request_counters[ip] = {
                "count": 0,
                "last_reset": current_time
            }
        
        # 如果上次重置时间超过时间窗口，重置计数
        if current_time - request_counters[ip]["last_reset"] > RATE_LIMIT_WINDOW:
            request_counters[ip] = {
                "count": 0,
                "last_reset": current_time
            }
        
        # 增加计数
        request_counters[ip]["count"] += 1
        
        # 检查是否超过限制
        return request_counters[ip]["count"] <= RATE_LIMIT

# 定期清理过期的请求计数器数据
def schedule_request_counter_cleanup():
    """定期清理过期的请求计数器数据，防止内存泄漏"""
    clean_old_request_data()
    # 每10分钟清理一次
    threading.Timer(600, schedule_request_counter_cleanup).start()

# 启动清理任务
schedule_request_counter_cleanup()

# 为图片生成短链接
def generate_short_link(filename, expire_minutes=None, db=None):
    """
    为图片生成短链接
    
    参数:
    - filename: 图片文件名
    - expire_minutes: 过期时间（分钟）
    - db: 数据库会话
    
    返回:
    - 短链接编码
    """
    # 生成随机短链接代码
    while True:
        code = ShortLink.generate_code()
        # 检查代码是否已存在
        existing = db.query(ShortLink).filter(ShortLink.code == code).first()
        if not existing:
            break
    
    # 计算过期时间
    expire_at = None
    if expire_minutes:
        expire_at = datetime.utcnow() + timedelta(minutes=expire_minutes)
    
    # 创建短链接记录
    short_link = ShortLink(
        code=code,
        target_file=filename,
        expire_at=expire_at
    )
    
    db.add(short_link)
    db.commit()
    
    return code

# 异步处理图片优化和检测
async def process_image(file_location: str, original_filename: str, client_ip: str, user_agent: str, db: Session) -> bool:
    """
    异步处理上传的图片：优化尺寸和内容检测
    
    返回True表示处理成功，False表示失败
    """
    loop = asyncio.get_event_loop()
    
    try:
        # 在线程池中执行图片优化（CPU密集型操作）
        await loop.run_in_executor(thread_pool, optimize_image, file_location)
        
        # 如果启用了离线检测，在线程池中执行检测
        if OFFLINE_CHECK_ENABLED:
            is_safe = await loop.run_in_executor(
                thread_pool, 
                lambda: offline_image_check(file_location, SKIN_THRESHOLD)
            )
            
            if not is_safe:
                # 删除不安全的图片
                os.remove(file_location)
                
                # 记录失败日志
                log_entry = UploadLog(
                    original_filename=original_filename,
                    status="failed",
                    error_message="图片内容不符合规范，已被拒绝（离线检测）",
                    ip_address=client_ip,
                    user_agent=user_agent
                )
                db.add(log_entry)
                db.commit()
                
                return False
        
        return True
    except Exception as e:
        logger.error(f"图片处理失败: {str(e)}")
        return False

# 图片上传接口
@router.post("/upload", tags=["图片"], summary="上传图片", description="上传图片文件并返回访问URL")
async def upload_image(
    file: UploadFile = File(..., description="要上传的图片文件"), 
    db: Session = Depends(get_db), 
    request: Request = None
):
    # 获取客户端IP和User-Agent
    client_ip = request.client.host if request else "unknown"
    user_agent = request.headers.get("user-agent", "") if request else ""
    
    # 使用信号量控制并发
    async with upload_semaphore:
        try:
            # 检查文件类型
            if not allowed_file(file.filename):
                error_message = f"不支持的图片格式: {file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else '未知格式'}。只允许上传以下格式: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                
                # 记录失败日志
                log_entry = UploadLog(
                    original_filename=file.filename,
                    status="failed",
                    error_message=error_message,
                    ip_address=client_ip,
                    user_agent=user_agent
                )
                db.add(log_entry)
                db.commit()
                
                raise HTTPException(
                    status_code=400,
                    detail=error_message
                )
            
            # 读取文件内容
            contents = await file.read()
            
            # 检查文件大小
            if len(contents) > MAX_SIZE:
                error_message = f"文件过大: {len(contents)/1024/1024:.2f}MB。文件大小不能超过{MAX_SIZE/1024/1024:.0f}MB"
                
                # 记录失败日志
                log_entry = UploadLog(
                    original_filename=file.filename,
                    status="failed",
                    error_message=error_message,
                    ip_address=client_ip,
                    user_agent=user_agent
                )
                db.add(log_entry)
                db.commit()
                
                raise HTTPException(
                    status_code=400,
                    detail=error_message
                )
            
            # 重置文件指针
            await file.seek(0)
            
            # 生成唯一文件名
            file_extension = file.filename.split('.')[-1].lower()
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            file_location = os.path.join(UPLOAD_DIR, unique_filename)
            
            # 确保上传目录存在
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            
            # 保存文件
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # 异步处理图片（优化和检测）
            is_processed = await process_image(
                file_location, 
                file.filename, 
                client_ip, 
                user_agent, 
                db
            )
            
            if not is_processed:
                # 如果处理失败，抛出异常
                raise HTTPException(
                    status_code=403,
                    detail="图片处理失败或内容不符合规范"
                )
            
            # 获取文件大小（KB）
            file_size = os.path.getsize(file_location) / 1024
            
            # 获取MIME类型
            import mimetypes
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
            
            # 记录上传成功日志
            log_entry = UploadLog(
                filename=unique_filename,
                original_filename=file.filename,
                mime_type=mime_type,
                size=file_size,
                status="success",
                ip_address=client_ip,
                user_agent=user_agent
            )
            db.add(log_entry)
            db.commit()
            
            # 为图片生成短链接
            short_code = generate_short_link(
                filename=unique_filename,
                db=db
            )
            
            # 动态生成URL
            if request:
                # 如果请求可用，从请求中构建URL
                host = request.headers.get("host", "localhost")
                scheme = request.headers.get("x-forwarded-proto", "http")
                base_url = f"{scheme}://{host}"
                file_url = f"{base_url}/images/{unique_filename}"
                short_url = f"{base_url}/s/{short_code}"
                
                # 记录上传信息到日志
                user_info = "匿名用户"
                logger.info(f"{client_ip} {user_info} 上传了 {file.filename}")
            else:
                # 如果请求不可用，使用环境变量中的BASE_URL
                file_url = f"{BASE_URL}/images/{unique_filename}"
                short_url = f"{BASE_URL}/s/{short_code}"
                
                # 记录上传信息到日志（无法获取IP时）
                user_info = "匿名用户"
                logger.info(f"未知IP {user_info} 上传了 {file.filename}")
            
            # 返回完整结果
            return {
                "url": file_url,
                "short_url": short_url,
                "filename": unique_filename,
                "original_filename": file.filename,
                "size": file_size,
                "mime_type": mime_type,
                "id": db_image.id,
                "html_code": f'<img src="{file_url}" alt="{file.filename}" />',
                "markdown_code": f"![{file.filename}]({file_url})"
            }
        except Exception as e:
            # 记录错误
            logger.error(f"上传失败: {str(e)}")
            
            # 记录到数据库日志
            try:
                log_entry = UploadLog(
                    original_filename=file.filename,
                    status="failed",
                    error_message=str(e),
                    ip_address=client_ip,
                    user_agent=user_agent
                )
                db.add(log_entry)
                db.commit()
            except:
                pass
            
            # 抛出HTTP异常
            raise HTTPException(
                status_code=500,
                detail=f"上传失败: {str(e)}"
            )

# 图片删除接口
@router.delete("/img/{filename}", tags=["图片"], summary="删除图片", description="删除已上传的图片")
async def delete_image(
    filename: str,
    db: Session = Depends(get_db)
):
    # 检查图片是否存在
    image = db.query(Image).filter(Image.filename == filename).first()
    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")
    
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    # 删除图片文件和数据库记录
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # 删除相关短链接
        db.query(ShortLink).filter(ShortLink.target_file == filename).delete()
        
        # 删除图片记录
        db.delete(image)
        db.commit()
        
        return {"success": True, "message": "图片已成功删除"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除图片时出错: {str(e)}")

# 短链接重定向
@router.get("/s/{code}", tags=["短链接"], summary="访问短链接", description="通过短链接代码访问图片")
async def access_short_link(code: str, db: Session = Depends(get_db)):
    # 查询短链接
    short_link = db.query(ShortLink).filter(ShortLink.code == code).first()
    if not short_link:
        raise HTTPException(status_code=404, detail="短链接不存在")
    
    # 检查是否过期
    if short_link.is_expired():
        raise HTTPException(status_code=410, detail="短链接已过期")
    
    # 增加访问计数
    short_link.increase_access_count()
    db.commit()
    
    # 重定向到原始图片
    return RedirectResponse(url=f"/images/{short_link.target_file}")

# 图片查看路由
@router.get("/images/{filename}", tags=["图片"], summary="查看图片", description="访问上传的图片")
async def view_image(filename: str, db: Session = Depends(get_db)):
    # 检查图片是否存在
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    
    # 获取图片MIME类型
    img_info = db.query(Image).filter(Image.filename == filename).first()
    content_type = img_info.mime_type if img_info else "image/jpeg"
    
    # 返回图片文件
    return FileResponse(
        file_path, 
        media_type=content_type,
        filename=img_info.original_filename if img_info else filename
    )

# 获取带水印的图片 - 使用线程池处理CPU密集型操作
@router.get("/images/{filename}/watermark", tags=["图片"], summary="获取带水印的图片", description="获取添加水印后的图片")
async def get_watermarked_image(
    filename: str, 
    text: str = "PicUI图床", 
    position: str = Query("bottom-right", description="水印位置，可选：center, bottom-right, bottom-left, top-right, top-left"),
    opacity: float = Query(0.5, ge=0.1, le=1.0, description="水印不透明度，范围0.1-1.0"),
    download: bool = Query(False, description="是否作为附件下载"),
    db: Session = Depends(get_db)
):
    # 检查图片是否存在
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    
    # 检查位置参数是否有效
    valid_positions = ["center", "bottom-right", "bottom-left", "top-right", "top-left"]
    if position not in valid_positions:
        position = "bottom-right"
    
    # 获取图片元数据
    img_info = db.query(Image).filter(Image.filename == filename).first()
    
    # 在线程池中运行水印添加（CPU密集型任务）
    loop = asyncio.get_event_loop()
    watermarked_img = await loop.run_in_executor(
        thread_pool,
        lambda: add_watermark(file_path, text, position, opacity)
    )
    
    if not watermarked_img:
        raise HTTPException(status_code=500, detail="添加水印失败")
    
    # 将图片转换为字节
    img_bytes = io.BytesIO()
    
    # 在线程池中运行图片保存操作
    await loop.run_in_executor(
        thread_pool,
        lambda: watermarked_img.save(img_bytes, format=watermarked_img.format or "JPEG")
    )
    
    img_bytes.seek(0)
    
    # 设置内容类型
    media_type = img_info.mime_type if img_info else "image/jpeg"
    
    # 根据是否下载设置响应头
    if download:
        filename_display = f"watermark_{filename}"
        headers = {"Content-Disposition": f'attachment; filename="{filename_display}"'}
    else:
        headers = {}
    
    return StreamingResponse(img_bytes, media_type=media_type, headers=headers)

# 创建临时外链
@router.post("/create-temp-link/{image_id}", tags=["短链接"], summary="创建临时外链", description="为图片创建带有有效期的临时外链")
async def create_temp_link(
    image_id: int,
    expire_minutes: int = Query(..., description="链接有效时间（分钟）", ge=1, le=10080),  # 最长7天
    request: Request = None,
    db: Session = Depends(get_db)
):
    # 查询图片
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")
    
    # 创建临时短链接
    code = generate_short_link(
        filename=image.filename,
        expire_minutes=expire_minutes,
        db=db
    )
    
    # 生成完整URL
    if request:
        base_url = f"{request.url.scheme}://{request.url.netloc}"
    else:
        base_url = BASE_URL
    
    short_url = f"{base_url}/s/{code}"
    
    # 计算到期时间
    expire_at = datetime.utcnow() + timedelta(minutes=expire_minutes)
    
    return {
        "short_url": short_url,
        "code": code,
        "expire_at": expire_at.isoformat(),
        "original_url": f"{base_url}/images/{image.filename}"
    } 