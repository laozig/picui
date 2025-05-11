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

# 上传图片路由
@router.post("/upload", tags=["图片"], summary="上传图片", description="上传图片文件并返回访问URL")
async def upload_image(
    file: Union[UploadFile, List[UploadFile]] = File(..., description="要上传的图片文件"), 
    db: Session = Depends(get_db), 
    request: Request = None
):
    """上传图片并返回访问URL"""
    # 检查是否是多文件上传
    is_multiple = isinstance(file, list)
    files = file if is_multiple else [file]
    
    results = []
    errors = []
    
    for single_file in files:
        # 获取客户端IP和User-Agent
        client_ip = request.client.host if request else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        try:
            # 检查图片类型
            if not allowed_file(single_file.filename):
                logger.warning(f"不支持的文件类型: {single_file.filename}")
                errors.append(f"不支持的图片格式: {single_file.filename}")
                continue
            
            # 生成安全文件名
            original_filename = single_file.filename
            ext = os.path.splitext(original_filename)[1].lower()
            random_filename = f"{uuid.uuid4().hex}{ext}"
            
            # 确保上传目录存在
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            
            # 保存图片
            file_location = os.path.join(UPLOAD_DIR, random_filename)
            
            # 边读取边写入以节省内存
            with open(file_location, "wb") as buffer:
                while True:
                    chunk = await single_file.read(8192)  # 每次读取8K
                    if not chunk:
                        break
                    buffer.write(chunk)
            
            logger.info(f"图片已保存: {file_location}")
            
            # 处理图片(检查、优化、存储信息)
            img_processing_succeeded = await process_image(
                file_location, 
                original_filename, 
                client_ip, 
                user_agent, 
                db
            )
            
            if not img_processing_succeeded:
                errors.append(f"图片处理失败: {original_filename}")
                # 删除图片文件
                try:
                    os.remove(file_location)
                except:
                    pass
                continue
            
            # 读取图片信息
            img_info = db.query(Image).filter(Image.filename == random_filename).first()
            
            # 为图片生成短链接
            short_code = generate_short_link(random_filename, db=db)
            
            # 构建基础URL
            if request:
                base_url = f"{request.url.scheme}://{request.url.netloc}"
            else:
                base_url = BASE_URL
            
            # 构建URL
            url = f"{base_url}/images/{random_filename}"
            short_url = f"{base_url}/s/{short_code}"
            
            # 构建HTML和Markdown代码
            html_code = f'<img src="{url}" alt="{original_filename}" />'
            markdown_code = f'![{original_filename}]({url})'
            
            # 添加到结果
            results.append({
                "url": url,
                "short_url": short_url,
                "filename": random_filename,
                "original_filename": original_filename,
                "size": img_info.size_kb if img_info else 0,
                "mime_type": img_info.mime_type if img_info else "image/jpeg",
                "id": img_info.id if img_info else 0,
                "html_code": html_code,
                "markdown_code": markdown_code
            })
        except Exception as e:
            logger.error(f"处理文件 {single_file.filename} 时出错: {str(e)}", exc_info=True)
            errors.append(f"处理文件失败: {single_file.filename}")
    
    # 处理返回结果
    if len(results) == 0:
        # 所有文件都处理失败
        error_message = "上传失败: " + ", ".join(errors)
        raise HTTPException(status_code=500, detail=error_message)
    
    # 如果只上传了一个文件且成功，返回单个结果
    if not is_multiple and len(results) == 1:
        return results[0]
    
    # 否则返回结果数组
    return results

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
    """通过短链接访问图片"""
    # 记录访问信息
    logger.info(f"短链接访问: code={code}")
    
    try:
        # 查询短链接
        short_link = db.query(ShortLink).filter(ShortLink.code == code).first()
        if not short_link:
            logger.warning(f"短链接不存在: code={code}")
            raise HTTPException(status_code=404, detail="短链接不存在")
        
        # 检查是否过期
        if short_link.is_expired():
            logger.warning(f"短链接已过期: code={code}, expire_at={short_link.expire_at}")
            raise HTTPException(status_code=410, detail="短链接已过期")
        
        # 检查目标文件是否存在
        file_path = os.path.join(UPLOAD_DIR, short_link.target_file)
        if not os.path.exists(file_path):
            logger.error(f"短链接指向的文件不存在: code={code}, file={short_link.target_file}, path={file_path}")
            raise HTTPException(status_code=404, detail="图片文件不存在或已被删除")
        
        try:
            # 增加访问计数
            short_link.increase_access_count()
            db.commit()
            
            # 获取图片信息，用于生成正确的MIME类型
            img_info = db.query(Image).filter(Image.filename == short_link.target_file).first()
            
            # 重定向到原始图片 - 采用两种方式尝试
            # 1. 优先使用文件响应直接返回图片，避免重定向
            if img_info:
                logger.info(f"短链接直接访问图片: code={code}, file={short_link.target_file}, mime={img_info.mime_type}")
                return FileResponse(
                    file_path, 
                    media_type=img_info.mime_type, 
                    filename=img_info.original_filename, 
                    content_disposition_type="inline"
                )
            
            # 2. 如果没有找到图片信息，使用重定向
            logger.info(f"短链接重定向: code={code} -> /images/{short_link.target_file}")
            return RedirectResponse(url=f"/images/{short_link.target_file}")
            
        except Exception as e:
            db.rollback()
            logger.error(f"短链接访问失败: code={code}, error={str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"访问短链接时发生错误: {str(e)}")
    except HTTPException:
        # 传递HTTP异常
        raise
    except Exception as e:
        logger.error(f"短链接处理异常: code={code}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理短链接时发生未知错误")

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
    
    # 返回图片文件，设置内容处理方式为inline以便在浏览器中查看而不是下载
    return FileResponse(
        file_path, 
        media_type=content_type,
        filename=img_info.original_filename if img_info else filename,
        content_disposition_type="inline"  # 添加此参数确保在浏览器中预览
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
    
    try:
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
            lambda: watermarked_img.save(img_bytes, format=watermarked_img.format or "JPEG", quality=95)
        )
        
        img_bytes.seek(0)
        
        # 设置内容类型 - 确保使用正确的MIME类型
        media_type = img_info.mime_type if img_info else "image/jpeg"
        
        # 生成文件名 - 用于下载时的文件名
        original_name = img_info.original_filename if img_info else filename
        filename_base = os.path.splitext(original_name)[0]
        ext = os.path.splitext(filename)[1] if "." in filename else ".jpg"
        download_filename = f"watermark_{filename_base}{ext}"
        
        # 根据是否下载设置响应头
        if download:
            headers = {
                "Content-Disposition": f'attachment; filename="{download_filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        else:
            # 修改预览模式的headers设置，禁用缓存以确保预览功能正常
            headers = {
                "Content-Disposition": f'inline; filename="{download_filename}"',
                "Cache-Control": "no-cache, no-store, must-revalidate",  # 禁用缓存
                "Pragma": "no-cache",
                "Expires": "0"
            }
        
        # 添加日志记录以便调试
        logger.info(f"水印图片准备返回: filename={filename}, download={download}, media_type={media_type}, headers={headers}")
        
        return StreamingResponse(
            img_bytes, 
            media_type=media_type, 
            headers=headers
        )
    except Exception as e:
        # 添加详细的错误日志
        logger.error(f"水印处理失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理水印图片时出错: {str(e)}")

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