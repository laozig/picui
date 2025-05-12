from fastapi import APIRouter, Depends, HTTPException, Request, Query, File, UploadFile, Response
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
from src.session import get_or_create_session, get_user_id

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
def generate_short_link(filename, expire_minutes=None, db=None, user_id=None):
    """
    为图片生成短链接
    
    参数:
    - filename: 图片文件名
    - expire_minutes: 过期时间（分钟）
    - db: 数据库会话
    - user_id: 用户ID
    
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
        expire_at=expire_at,
        user_id=user_id  # 添加用户ID
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
        result = await loop.run_in_executor(thread_pool, optimize_image, file_location)
        if result:
            logger.debug(f"✓ 图片已优化: {os.path.basename(file_location)} {result}")
        
        # 如果启用了离线检测，在线程池中执行检测
        if OFFLINE_CHECK_ENABLED:
            logger.debug(f"执行图片内容检测: {os.path.basename(file_location)}")
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
                
                logger.warning(f"图片内容不符合规范，已被拒绝: {os.path.basename(file_location)}")
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
    request: Request = None,
    response: Response = None
):
    """上传图片并返回访问URL"""
    # 获取或创建会话
    _, user_id = get_or_create_session(request, response)
    
    # 检查是否是多文件上传
    is_multiple = isinstance(file, list)
    files = file if is_multiple else [file]
    
    results = []
    errors = []
    
    for single_file in files:
        # 获取客户端IP和User-Agent
        client_ip = request.client.host if request else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # 检查文件类型是否符合要求
        original_filename = single_file.filename
        if not allowed_file(original_filename):
            error_message = f"不支持的文件类型: {original_filename}"
            logger.warning(f"{error_message}")
            errors.append({"file": original_filename, "error": error_message})
            continue
        
        # 检查文件大小
        file_size = await single_file.read(MAX_SIZE + 1)  # 读取比最大限制多1字节，用于检测是否超过限制
        if len(file_size) > MAX_SIZE:
            error_message = f"文件大小超过限制 ({len(file_size) / 1024 / 1024:.1f}MB > {MAX_SIZE / 1024 / 1024:.1f}MB)"
            logger.warning(f"{error_message}: {original_filename}")
            errors.append({"file": original_filename, "error": error_message})
            continue
        
        # 重置文件指针
        await single_file.seek(0)
        
        # 生成唯一文件名，保留原始扩展名
        file_extension = os.path.splitext(original_filename)[1].lower()
        filename = f"{uuid.uuid4().hex}{file_extension}"
        file_location = os.path.join(UPLOAD_DIR, filename)
        
        try:
            # 限制并发上传数
            async with upload_semaphore:
                # 确保目录存在
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                
                # 写入文件
                with open(file_location, "wb+") as file_object:
                    file_object.write(file_size)
                
                # 获取文件大小
                file_size_kb = os.path.getsize(file_location) / 1024
                
                # 异步处理图片（优化尺寸和内容检测）
                if not await process_image(file_location, original_filename, client_ip, user_agent, db):
                    errors.append({"file": original_filename, "error": "图片处理失败"})
                    continue
                
                # 保存图片记录到数据库
                try:
                    # 创建Image对象，但不包括可能缺失的字段
                    img = Image(
                        filename=filename,
                        original_filename=original_filename,
                        user_id=user_id  # 添加用户ID
                    )
                    
                    # 尝试设置可能缺失的字段
                    try:
                        img.file_size = file_size_kb
                    except Exception:
                        logger.warning(f"无法设置file_size字段，数据库可能不支持该字段")
                    
                    try:
                        img.upload_ip = client_ip
                    except Exception:
                        logger.warning(f"无法设置upload_ip字段，数据库可能不支持该字段")
                    
                    try:
                        img.mime_type = "image/jpeg"
                    except Exception:
                        logger.warning(f"无法设置mime_type字段，数据库可能不支持该字段")
                    
                    db.add(img)
                    try:
                        db.commit()
                    except Exception as db_error:
                        # 如果提交失败，可能是表结构问题
                        db.rollback()
                        logger.warning(f"提交图片记录失败: {str(db_error)}")
                        
                        # 尝试使用最小字段集再次插入
                        if "no such column" in str(db_error):
                            # 表结构不匹配的特定错误，尝试不包含可能缺失的字段
                            logger.warning(f"数据库表结构不匹配，尝试使用最小字段集")
                            try:
                                # 执行原始SQL插入，只使用基本字段
                                from sqlalchemy import text
                                sql = text("INSERT INTO images (filename, original_filename, user_id) VALUES (:filename, :orig_filename, :user_id)")
                                db.execute(sql, {"filename": filename, "orig_filename": original_filename, "user_id": user_id})
                                db.commit()
                                logger.info(f"使用最小字段集插入图片记录成功")
                            except Exception as minimal_error:
                                logger.error(f"使用最小字段集插入图片记录失败: {str(minimal_error)}")
                                # 如果仍然失败，抛出异常
                                raise
                        else:
                            # 其他数据库错误，重新抛出
                            raise
                
                except Exception as e:
                    logger.error(f"保存图片记录到数据库时出错: {str(e)}")
                    # 如果文件已创建但处理失败，删除文件
                    if os.path.exists(file_location):
                        try:
                            os.remove(file_location)
                        except:
                            pass
                    
                    # 记录错误
                    errors.append({"file": original_filename, "error": str(e)})
                    
                    # 记录上传失败日志
                    log_entry = UploadLog(
                        original_filename=original_filename,
                        status="failed",
                        error_message=str(e),
                        ip_address=client_ip,
                        user_agent=user_agent,
                        user_id=user_id  # 添加用户ID
                    )
                    db.add(log_entry)
                    try:
                        db.commit()
                    except Exception as db_error:
                        db.rollback()
                        logger.error(f"记录上传失败日志时出错: {str(db_error)}")
                        try:
                            # 尝试不附加额外字段再次提交
                            db.add(UploadLog(
                                original_filename=original_filename,
                                status="failed",
                                error_message=str(e)[:200],  # 限制错误消息长度
                                ip_address=client_ip,
                                user_id=user_id
                            ))
                            db.commit()
                        except Exception:
                            # 如果仍然失败，放弃记录日志，但不影响主流程
                            logger.error("无法记录上传失败日志，继续处理")
                            db.rollback()
                
                # 记录上传成功日志
                log_entry = UploadLog(
                    original_filename=original_filename,
                    status="success",
                    ip_address=client_ip,
                    user_agent=user_agent,
                    user_id=user_id  # 添加用户ID
                )
                
                # 尝试设置可能缺失的字段
                try:
                    log_entry.saved_filename = filename
                except Exception:
                    logger.warning(f"无法设置saved_filename字段，数据库可能不支持该字段")
                
                try:
                    log_entry.file_size = file_size_kb
                except Exception:
                    logger.warning(f"无法设置file_size字段，数据库可能不支持该字段")
                
                db.add(log_entry)
                try:
                    db.commit()
                except Exception as db_error:
                    # 如果提交失败，可能是表结构问题
                    db.rollback()
                    logger.warning(f"记录上传日志时出错: {str(db_error)}")
                    
                    # 尝试使用最小字段集
                    if "no such column" in str(db_error):
                        try:
                            # 执行原始SQL插入，只使用基本字段
                            from sqlalchemy import text
                            sql = text("INSERT INTO upload_logs (original_filename, status, ip_address, user_id) VALUES (:orig_filename, :status, :ip, :user_id)")
                            db.execute(sql, {
                                "orig_filename": original_filename, 
                                "status": "success", 
                                "ip": client_ip, 
                                "user_id": user_id
                            })
                            db.commit()
                            logger.info(f"使用最小字段集记录上传日志成功")
                        except Exception as minimal_error:
                            logger.error(f"使用最小字段集记录上传日志失败: {str(minimal_error)}")
                            # 记录错误但不抛出异常，继续处理
                    else:
                        # 其他错误记录但不抛出
                        logger.error(f"记录上传日志时出错: {str(db_error)}")
                
                # 生成访问URL
                access_url = f"{BASE_URL}/images/{filename}"
                
                # 添加到结果列表
                logger.debug(f"✓ 文件上传成功: {filename} ({file_size_kb:.1f} KB)")
                results.append({
                    "url": access_url,
                    "filename": filename,
                    "original_filename": original_filename,
                    "size": file_size_kb
                })
                
        except Exception as e:
            logger.error(f"文件上传处理异常: {str(e)}")
            # 如果文件已创建但处理失败，删除文件
            if os.path.exists(file_location):
                try:
                    os.remove(file_location)
                except:
                    pass
            
            # 记录错误
            errors.append({"file": original_filename, "error": str(e)})
            
            # 记录上传失败日志
            log_entry = UploadLog(
                original_filename=original_filename,
                status="failed",
                error_message=str(e),
                ip_address=client_ip,
                user_agent=user_agent,
                user_id=user_id  # 添加用户ID
            )
            db.add(log_entry)
            try:
                db.commit()
            except Exception as db_error:
                db.rollback()
                logger.error(f"记录上传失败日志时出错: {str(db_error)}")
                try:
                    # 尝试不附加额外字段再次提交
                    db.add(UploadLog(
                        original_filename=original_filename,
                        status="failed",
                        error_message=str(e)[:200],  # 限制错误消息长度
                        ip_address=client_ip,
                        user_id=user_id
                    ))
                    db.commit()
                except Exception:
                    # 如果仍然失败，放弃记录日志，但不影响主流程
                    logger.error("无法记录上传失败日志，继续处理")
                    db.rollback()
    
    # 返回结果
    if is_multiple:
        return {"success": len(results) > 0, "files": results, "errors": errors}
    else:
        # 单文件上传
        if errors:
            raise HTTPException(status_code=400, detail=errors[0]["error"])
        return results[0]

# 图片删除接口
@router.delete("/img/{filename}", tags=["图片"], summary="删除图片", description="删除已上传的图片")
async def delete_image(
    filename: str,
    db: Session = Depends(get_db),
    request: Request = None
):
    # 获取用户ID
    user_id = get_user_id(request)
    
    # 检查图片是否存在
    image = db.query(Image).filter(Image.filename == filename).first()
    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")
    
    # 检查是否是上传者本人
    if user_id and image.user_id != user_id:
        raise HTTPException(status_code=403, detail="您无权删除其他用户上传的图片")
    
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
    response: Response = None,
    db: Session = Depends(get_db)
):
    # 获取或创建会话
    _, user_id = get_or_create_session(request, response)
    
    # 查询图片
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")
    
    # 检查权限 - 只能为自己的图片创建外链
    if user_id and image.user_id != user_id:
        raise HTTPException(status_code=403, detail="您无权为其他用户的图片创建外链")
    
    # 创建临时短链接
    code = generate_short_link(
        filename=image.filename,
        expire_minutes=expire_minutes,
        db=db,
        user_id=user_id
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