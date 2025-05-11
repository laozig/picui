from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request, Form, BackgroundTasks, Cookie, Response, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import shutil
import os
from typing import List, Dict, Optional, Set, Union
import uuid
from sqlalchemy.orm import Session
import mimetypes
import time
import logging
import asyncio
from datetime import datetime, timedelta
import secrets
import glob
import pyotp
import qrcode
import io
import base64
import requests
import json
import hmac
import hashlib
from ipaddress import IPv4Network, IPv4Address
from pathlib import Path
from PIL import Image
import numpy as np
import threading
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry

from database import get_db, create_tables, Image, User, UploadLog, ShortLink, create_admin_user

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
API_TOKEN = os.getenv("API_TOKEN", "mysecrettoken")  # 默认token值，用于兼容旧版本

# 管理员登录信息
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "123456")

# 会话存储
active_sessions = {}

# IP白名单配置
IP_WHITELIST = os.getenv("IP_WHITELIST", "127.0.0.1/32,192.168.0.0/16,10.0.0.0/8").split(",")
IP_WHITELIST_NETWORKS = [IPv4Network(ip.strip()) for ip in IP_WHITELIST]

# 防盗链配置
ALLOWED_REFERERS = os.getenv("ALLOWED_REFERERS", "localhost,127.0.0.1").split(",")

# 阿里云内容安全配置
ALIYUN_ACCESS_KEY_ID = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
ALIYUN_ACCESS_KEY_SECRET = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
ALIYUN_REGION = os.getenv("ALIYUN_REGION", "cn-shanghai")
CONTENT_CHECK_ENABLED = os.getenv("CONTENT_CHECK_ENABLED", "false").lower() == "true"
# 使用离线检测（简单肤色检测，不依赖云服务）
OFFLINE_CHECK_ENABLED = os.getenv("OFFLINE_CHECK_ENABLED", "false").lower() == "true"
# 肤色检测阈值，超过此比例的肤色像素将被标记为不适当内容
SKIN_THRESHOLD = float(os.getenv("SKIN_THRESHOLD", "0.5"))

# 并发控制配置
MAX_CONCURRENT_UPLOADS = int(os.getenv("MAX_CONCURRENT_UPLOADS", 20))  # 最大并发上传数
# 创建信号量控制并发
upload_semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)

# 磁盘空间检查配置
DISK_CHECK_INTERVAL = int(os.getenv("DISK_CHECK_INTERVAL", 3600))  # 默认每小时检查一次
DISK_USAGE_THRESHOLD = float(os.getenv("DISK_USAGE_THRESHOLD", 80.0))  # 默认阈值80%

# 设置Prometheus指标
try:
    # 尝试初始化Prometheus计数器
    from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
    
    # 创建自定义注册表
    registry = CollectorRegistry()
    
    UPLOAD_COUNTER = Counter('pic_uploads_total', '总上传次数', registry=registry)
    UPLOAD_FAILURE_COUNTER = Counter('pic_upload_failures_total', '上传失败次数', registry=registry)
    DELETE_COUNTER = Counter('pic_deletions_total', '删除次数', registry=registry)
    DISK_USAGE_GAUGE = Gauge('pic_disk_usage_percent', '上传目录磁盘使用率', registry=registry)
    UPLOAD_SIZE_GAUGE = Gauge('pic_upload_size_bytes', '上传文件大小(字节)', registry=registry)
    
    # 启用Prometheus监控
    PROMETHEUS_ENABLED = True
except Exception as e:
    # 如果Prometheus初始化失败，使用空类模拟计数器行为
    print(f"Prometheus初始化失败: {str(e)}")
    PROMETHEUS_ENABLED = False
    
    class DummyCounter:
        def inc(self, amount=1):
            pass
    
    class DummyGauge:
        def set(self, value):
            pass
    
    UPLOAD_COUNTER = DummyCounter()
    UPLOAD_FAILURE_COUNTER = DummyCounter()
    DELETE_COUNTER = DummyCounter()
    DISK_USAGE_GAUGE = DummyGauge()
    UPLOAD_SIZE_GAUGE = DummyGauge()
    
    def generate_latest(registry=None):
        return b""

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
        {"name": "用户", "description": "用户注册、登录和管理"}
    ]
)

# 配置模板目录
templates = Jinja2Templates(directory="templates")

# 确保上传目录存在
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 允许的图片格式
ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp", 
    "bmp", "tiff", "tif", "svg", "ico", 
    "heic", "heif", "avif", "jfif", "pjpeg", "pjp"
}

# 支持的MIME类型
supported_mimetypes = [
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/bmp", "image/tiff", "image/svg+xml", "image/x-icon",
    "image/heic", "image/heif", "image/avif"
]

# 友好显示的MIME类型
supported_mimetypes_friendly = [
    "JPEG", "PNG", "GIF", "WEBP",
    "BMP", "TIFF", "SVG", "ICO",
    "HEIC", "HEIF", "AVIF"
]

# 文件大小限制 (修改为15MB)
MAX_SIZE = int(os.getenv("MAX_FILE_SIZE", 15 * 1024 * 1024))  # 默认15MB
max_file_size_kb = MAX_SIZE / 1024  # 转换为KB

# 频率限制配置
RATE_LIMIT = int(os.getenv("RATE_LIMIT", 20))  # 每分钟最大请求数
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 60))  # 时间窗口（秒）

# 请求计数器记录
request_counters = {}

# 清理过期的请求计数记录
def clean_old_request_data():
    """清理过期的请求计数记录"""
    current_time = time.time()
    expired_keys = []
    
    for key, data in request_counters.items():
        if current_time - data["last_reset"] > RATE_LIMIT_WINDOW:
            expired_keys.append(key)
    
    for key in expired_keys:
        del request_counters[key]

# 检查请求频率是否超限
def check_rate_limit(ip, current_time):
    """
    检查IP请求频率是否超限
    
    返回True表示未超限，False表示已超限
    """
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

# 检查磁盘空间利用率
def check_disk_usage():
    try:
        upload_path = os.path.abspath(UPLOAD_DIR)
        
        # 获取目录所在分区的总空间和可用空间
        total, used, free = shutil.disk_usage(upload_path)
        
        # 计算利用率百分比
        usage_percent = (used / total) * 100
        
        # 更新Prometheus指标
        DISK_USAGE_GAUGE.set(usage_percent)
        
        logger.info(f"磁盘使用率检查: {usage_percent:.2f}% (总空间: {total/1024/1024/1024:.2f}GB, 已用: {used/1024/1024/1024:.2f}GB)")
        
        # 如果利用率超过阈值，记录警告
        if usage_percent > DISK_USAGE_THRESHOLD:
            warning_msg = f"警告: 磁盘空间使用率已达 {usage_percent:.2f}%，超过设定阈值 {DISK_USAGE_THRESHOLD}%"
            logger.warning(warning_msg)
            # 这里可以添加发送邮件的代码，现在用logging.warning代替
        
        # 计划下一次检查
        threading.Timer(DISK_CHECK_INTERVAL, check_disk_usage).start()
    except Exception as e:
        logger.error(f"检查磁盘空间时出错: {str(e)}")
        # 即使出错，也要尝试再次调度
        threading.Timer(DISK_CHECK_INTERVAL, check_disk_usage).start()

# 在应用启动时创建数据库表和管理员账户
@app.on_event("startup")
def startup_event():
    create_tables()
    db = next(get_db())
    create_admin_user(db)
    # 启动磁盘空间检查
    check_disk_usage()

# 简单的离线图片内容检测
def offline_image_check(file_path: str) -> bool:
    """
    简单的离线图片检测函数，主要检测肤色比例
    返回True表示安全，False表示不安全

    注意: 这是一个非常基础的检测方法，不能替代专业的内容审核服务
    """
    try:
        # 打开图片
        img = Image.open(file_path)
        
        # 缩放以提高性能
        img = img.resize((100, int(100 * img.height / img.width)))
        
        # 转换为numpy数组
        img_array = np.array(img)
        
        # 检查是否为RGB图像
        if len(img_array.shape) < 3 or img_array.shape[2] < 3:
            return True  # 不是彩色图像，可能是黑白或灰度图，视为安全
        
        # 提取R, G, B通道
        r, g, b = img_array[:,:,0], img_array[:,:,1], img_array[:,:,2]
        
        # 简单的肤色检测 (不是非常精确，但足够做基本过滤)
        # 基于RGB颜色空间的肤色范围
        skin_mask = (r > 95) & (g > 40) & (b > 20) & \
                    ((np.maximum(r, np.maximum(g, b)) - np.minimum(r, np.minimum(g, b))) > 15) & \
                    (np.abs(r - g) > 15) & (r > g) & (r > b)
        
        # 计算肤色像素占比
        skin_ratio = np.sum(skin_mask) / skin_mask.size
        
        # 如果肤色像素比例超过阈值，可能是不适当内容
        if skin_ratio > SKIN_THRESHOLD:
            logger.warning(f"离线检测: 图片 {file_path} 可能包含不适当内容 (肤色比例: {skin_ratio:.2f})")
            return False
            
        return True
    except Exception as e:
        logger.error(f"离线图片检测出错: {str(e)}")
        return True  # 出错时默认通过

# 阿里云内容安全检测函数
async def check_image_content(file_path: str) -> bool:
    """
    使用阿里云内容安全检测图片是否违规
    返回True表示安全，False表示不安全
    """
    # 如果未启用内容检查，直接返回安全
    if not CONTENT_CHECK_ENABLED or not ALIYUN_ACCESS_KEY_ID or not ALIYUN_ACCESS_KEY_SECRET:
        return True
        
    try:
        # 读取图片并转换为Base64
        with open(file_path, 'rb') as f:
            img_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        # 构建请求数据
        post_data = {
            "scenes": ["porn", "terrorism", "ad", "live", "qrcode"],
            "tasks": [
                {
                    "dataId": str(uuid.uuid4()),
                    "url": "",
                    "time": int(time.time() * 1000),
                    "content": img_base64
                }
            ]
        }
        
        # 准备请求URL和headers
        url = f"https://green.cn-{ALIYUN_REGION}.aliyuncs.com/green/image/scan"
        content_type = "application/json"
        
        # 当前GMT时间
        gmt_time = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        # 计算签名
        body_str = json.dumps(post_data)
        
        # 准备签名字符串
        string_to_sign = "POST\n"
        string_to_sign += "application/json\n"
        string_to_sign += "\n"  # 如果有ContentMD5，这里应该放ContentMD5
        string_to_sign += content_type + "\n"
        string_to_sign += gmt_time + "\n"
        string_to_sign += "/green/image/scan"
        
        # 计算HMAC-SHA1签名
        hmac_obj = hmac.new(
            ALIYUN_ACCESS_KEY_SECRET.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        )
        signature = base64.b64encode(hmac_obj.digest()).decode('utf-8')
        
        # 准备Authorization Header
        auth_header = f"acs {ALIYUN_ACCESS_KEY_ID}:{signature}"
        
        # 设置HTTP请求头
        headers = {
            "Accept": "application/json",
            "Content-Type": content_type,
            "Content-Length": str(len(body_str)),
            "Date": gmt_time,
            "Authorization": auth_header
        }
        
        # 发送请求
        response = requests.post(url, data=body_str, headers=headers)
        result = response.json()
        
        # 分析结果
        if result and 'data' in result and len(result['data']) > 0:
            for task_result in result['data']:
                if task_result['code'] == 200:
                    for scene, scene_results in task_result.get('results', {}).items():
                        for item in scene_results:
                            if item.get('suggestion') in ['block', 'review']:
                                logger.warning(f"图片检测不通过: {file_path}, 场景: {scene}, 建议: {item['suggestion']}")
                                return False
            logger.info(f"图片检测通过: {file_path}")
            return True
        
        logger.warning(f"图片检测失败: {file_path}, 响应: {result}")
        # 检测失败时，保守起见返回False
        return False
    except Exception as e:
        logger.error(f"图片内容检测出错: {str(e)}")
        # 出错时默认返回True以避免服务中断，可根据需求调整
        return True

# 检查文件格式是否允许
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 频率限制中间件
def rate_limit(request: Request):
    client_ip = request.client.host
    current_time = datetime.now()
    
    # 检查是否超过限制
    if not check_rate_limit(client_ip, current_time.timestamp()):
        reset_time = datetime.fromtimestamp(request_counters[client_ip]["last_reset"] + RATE_LIMIT_WINDOW)
        retry_after = int((reset_time - current_time).total_seconds())
        
        # 清理过期的IP记录（可选，防止内存泄漏）
        clean_old_request_data()
        
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后再试",
            headers={"Retry-After": str(retry_after)}
        )
    
    return True

# 验证token的依赖函数（兼容旧版本和新版本）
def verify_token(token: str = Form(...), db: Session = Depends(get_db)):
    # 首先检查是否为管理员token
    if token == API_TOKEN:
        return {"valid": True, "user": None}
    
    # 检查是否为用户API token
    user = db.query(User).filter(User.api_token == token).first()
    if user:
        return {"valid": True, "user": user}
    
    # 如果都不是，则验证失败
    raise HTTPException(
        status_code=403,
        detail="无效的访问令牌"
    )

# 验证会话的依赖函数
def verify_session(session_id: Optional[str] = Cookie(None)):
    if not session_id or session_id not in active_sessions:
        raise HTTPException(
            status_code=401,
            detail="未登录或会话已过期"
        )
    return active_sessions[session_id]

# 验证是否为管理员
def verify_admin(session_data = Depends(verify_session)):
    if not session_data.get("is_admin", False):
        raise HTTPException(
            status_code=403,
            detail="需要管理员权限"
        )
    return session_data

# 验证请求IP是否在白名单中
def verify_ip_whitelist(request: Request):
    client_ip = request.client.host
    try:
        client_ip_obj = IPv4Address(client_ip)
        for network in IP_WHITELIST_NETWORKS:
            if client_ip_obj in network:
                return True
        # IP不在白名单中
        raise HTTPException(
            status_code=403,
            detail="您的IP地址无权访问此资源"
        )
    except ValueError:
        # 无效的IP地址
        raise HTTPException(
            status_code=403,
            detail="无法验证您的IP地址"
        )

# 获取当前登录用户
def get_current_user(session_data = Depends(verify_session), db: Session = Depends(get_db)):
    user_id = session_data.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="未找到用户信息"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=401,
            detail="用户不存在"
        )
    
    return user

# 获取当前用户（可选）
async def get_current_user_optional(
    request: Request,
    session_id: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not session_id or session_id not in active_sessions:
        return None
    
    user_id = active_sessions[session_id].get("user_id")
    if not user_id:
        return None
    
    user = db.query(User).filter(User.id == user_id).first()
    return user

# 图片处理函数

def optimize_image(img_path, max_size=1920, max_dimension=5000):
    """
    优化图片：
    1. 限制最长边不超过max_size（默认1920px）
    2. 确保宽高不超过max_dimension（默认5000px）
    3. 保持原比例
    
    返回是否修改了图片
    """
    try:
        with Image.open(img_path) as img:
            original_width, original_height = img.size
            
            # 检查是否需要调整尺寸
            width, height = original_width, original_height
            
            # 检查是否超过最大尺寸限制
            if width > max_dimension or height > max_dimension:
                # 计算缩放比例
                scale = min(max_dimension / width, max_dimension / height)
                width = int(width * scale)
                height = int(height * scale)
            
            # 检查最长边是否超过限制
            longest_side = max(width, height)
            if longest_side > max_size:
                # 计算缩放比例
                scale = max_size / longest_side
                width = int(width * scale)
                height = int(height * scale)
            
            # 如果尺寸没有变化，不需要调整
            if width == original_width and height == original_height:
                return False
            
            # 调整图片尺寸
            img = img.resize((width, height), Image.LANCZOS)
            
            # 保存优化后的图片，保持原格式
            img.save(img_path, quality=90, optimize=True)
            return True
    except Exception as e:
        logger.error(f"图片优化失败: {str(e)}")
        return False

def add_watermark(img_path, text, position="center", opacity=0.5, output_path=None):
    """
    为图片添加文字水印
    
    参数:
    - img_path: 原图片路径
    - text: 水印文字
    - position: 水印位置 (center, bottom-right, bottom-left, top-right, top-left)
    - opacity: 水印不透明度 (0-1)
    - output_path: 输出文件路径，None则返回图片对象不保存
    
    返回:
    - 如果output_path为None，返回处理后的图片对象
    - 否则保存图片并返回True/False表示成功/失败
    """
    try:
        # 打开原图片
        with Image.open(img_path) as img:
            # 创建一个透明的图层作为水印
            watermark = Image.new('RGBA', img.size, (0, 0, 0, 0))
            
            # 创建绘图对象
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(watermark)
            
            # 尝试加载系统字体
            try:
                # 对于Windows系统
                font = ImageFont.truetype('arial.ttf', size=int(min(img.size) / 20))
            except:
                try:
                    # 对于Linux系统
                    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size=int(min(img.size) / 20))
                except:
                    # 降级到默认字体
                    font = ImageFont.load_default()
            
            # 获取文本大小 - 使用textbbox或fallback到textsize
            try:
                # 新版Pillow使用textbbox
                left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
                text_width = right - left
                text_height = bottom - top
            except AttributeError:
                # 旧版Pillow使用textsize
                text_width, text_height = draw.textsize(text, font=font)
            
            # 根据position确定水印位置
            if position == "center":
                position = ((img.size[0] - text_width) / 2, (img.size[1] - text_height) / 2)
            elif position == "bottom-right":
                position = (img.size[0] - text_width - 20, img.size[1] - text_height - 20)
            elif position == "bottom-left":
                position = (20, img.size[1] - text_height - 20)
            elif position == "top-right":
                position = (img.size[0] - text_width - 20, 20)
            elif position == "top-left":
                position = (20, 20)
            
            # 绘制水印文字，半透明黑色背景
            padding = 10
            draw.rectangle(
                [
                    position[0] - padding, 
                    position[1] - padding, 
                    position[0] + text_width + padding, 
                    position[1] + text_height + padding
                ], 
                fill=(0, 0, 0, int(128 * opacity))
            )
            
            # 绘制水印文字，白色
            draw.text(position, text, font=font, fill=(255, 255, 255, int(255 * opacity)))
            
            # 确保原图有alpha通道
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # 合并原图和水印
            result = Image.alpha_composite(img, watermark)
            
            # 转回原来的模式
            if img.mode != 'RGBA':
                result = result.convert(img.mode)
            
            # 如果指定了输出路径，则保存图片
            if output_path:
                result.save(output_path)
                return True
            else:
                return result
    except Exception as e:
        logger.error(f"添加水印失败: {str(e)}")
        if output_path:
            return False
        return None

def generate_short_link(filename, user_id=None, expire_minutes=None, db=None):
    """
    为图片生成短链接
    
    参数:
    - filename: 图片文件名
    - user_id: 用户ID
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
        expire_at=expire_at,
        user_id=user_id
    )
    
    db.add(short_link)
    db.commit()
    
    return code

# 验证图片内容
def is_valid_image(content):
    """
    检查内容是否为有效的图片
    """
    try:
        # 创建内存文件对象
        image_stream = io.BytesIO(content)
        # 尝试打开图片
        img = Image.open(image_stream)
        # 验证图片格式
        img.verify()
        return True
    except Exception:
        return False

# 修改上传路由，添加图片处理功能
@app.post("/upload", tags=["图片"], summary="上传图片", description="上传图片文件并返回访问URL")
async def upload_image(
    file: UploadFile = File(..., description="要上传的图片文件"), 
    token_data = Depends(verify_token),
    db: Session = Depends(get_db), 
    request: Request = None,
    _: bool = Depends(rate_limit)  # 添加频率限制依赖
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
                    user_agent=user_agent,
                    user_id=token_data["user"].id if token_data["user"] else None
                )
                db.add(log_entry)
                db.commit()
                
                # 更新Prometheus指标
                UPLOAD_FAILURE_COUNTER.inc()
                
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
                    user_agent=user_agent,
                    user_id=token_data["user"].id if token_data["user"] else None
                )
                db.add(log_entry)
                db.commit()
                
                # 更新Prometheus指标
                UPLOAD_FAILURE_COUNTER.inc()
                
                raise HTTPException(
                    status_code=400,
                    detail=error_message
                )
            
            # 更新Prometheus指标
            UPLOAD_SIZE_GAUGE.set(len(contents))
            
            # 重置文件指针
            await file.seek(0)
            
            # 生成唯一文件名
            file_extension = file.filename.split('.')[-1].lower()
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            file_location = os.path.join(UPLOAD_DIR, unique_filename)
            
            # 保存文件
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # 优化图片尺寸
            optimize_image(file_location)
            
            # 内容安全检测
            is_safe = True
            
            # 如果启用了离线检测，先进行离线检测
            if OFFLINE_CHECK_ENABLED:
                is_safe = offline_image_check(file_location)
                if not is_safe:
                    # 删除不安全的图片
                    os.remove(file_location)
                    
                    # 记录失败日志
                    log_entry = UploadLog(
                        original_filename=file.filename,
                        status="failed",
                        error_message="图片内容不符合规范，已被拒绝（离线检测）",
                        ip_address=client_ip,
                        user_agent=user_agent,
                        user_id=token_data["user"].id if token_data["user"] else None
                    )
                    db.add(log_entry)
                    db.commit()
                    
                    # 更新Prometheus指标
                    UPLOAD_FAILURE_COUNTER.inc()
                    
                    raise HTTPException(
                        status_code=403,
                        detail="图片内容不符合规范，已被拒绝（离线检测）"
                    )
            
            # 如果启用了阿里云内容安全检测，进行云端检测
            if CONTENT_CHECK_ENABLED:
                is_safe = await check_image_content(file_location)
                if not is_safe:
                    # 删除不安全的图片
                    os.remove(file_location)
                    
                    # 记录失败日志
                    log_entry = UploadLog(
                        original_filename=file.filename,
                        status="failed",
                        error_message="图片内容不符合规范，已被拒绝（云端检测）",
                        ip_address=client_ip,
                        user_agent=user_agent,
                        user_id=token_data["user"].id if token_data["user"] else None
                    )
                    db.add(log_entry)
                    db.commit()
                    
                    # 更新Prometheus指标
                    UPLOAD_FAILURE_COUNTER.inc()
                    
                    raise HTTPException(
                        status_code=403,
                        detail="图片内容不符合规范，已被拒绝（云端检测）"
                    )
            
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
            
            # 关联用户（如果有）
            if token_data["user"]:
                db_image.user_id = token_data["user"].id
            
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
                user_agent=user_agent,
                user_id=token_data["user"].id if token_data["user"] else None
            )
            db.add(log_entry)
            db.commit()
            
            # 更新Prometheus指标
            UPLOAD_COUNTER.inc()
            
            # 为图片生成短链接
            short_code = generate_short_link(
                filename=unique_filename,
                user_id=token_data["user"].id if token_data["user"] else None,
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
                user_info = f"用户:{token_data['user'].username}" if token_data["user"] else "未知用户"
                logger.info(f"{client_ip} {user_info} 上传了 {file.filename}")
            else:
                # 如果不可用，使用配置的BASE_URL
                file_url = f"{BASE_URL}/images/{unique_filename}"
                short_url = f"{BASE_URL}/s/{short_code}"
                
                # 记录上传信息到日志（无法获取IP时）
                user_info = f"用户:{token_data['user'].username}" if token_data["user"] else "未知用户"
                logger.info(f"未知IP {user_info} 上传了 {file.filename}")
            
            return {
                "url": file_url, 
                "filename": unique_filename, 
                "id": db_image.id,
                "short_url": short_url,
                "short_code": short_code
            }
            
        except HTTPException:
            raise
        except Exception as e:
            # 记录错误
            logger.error(f"上传过程中出错: {str(e)}")
            
            # 记录失败日志
            try:
                log_entry = UploadLog(
                    original_filename=file.filename if hasattr(file, 'filename') else "unknown",
                    status="failed",
                    error_message=str(e),
                    ip_address=client_ip,
                    user_agent=user_agent,
                    user_id=token_data["user"].id if token_data["user"] and hasattr(token_data, "user") else None
                )
                db.add(log_entry)
                db.commit()
                
                # 更新Prometheus指标
                UPLOAD_FAILURE_COUNTER.inc()
            except Exception as log_error:
                logger.error(f"记录错误日志时出错: {str(log_error)}")
            
            raise HTTPException(
                status_code=500,
                detail=f"上传过程中出错: {str(e)}"
            )

# 删除图片
@app.delete("/img/{filename}")
async def delete_image(
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 检查图片是否存在
    db_image = db.query(Image).filter(Image.filename == filename).first()
    if not db_image:
        raise HTTPException(status_code=404, detail="图片未找到")
    
    # 检查权限
    if not user.is_admin and (db_image.user_id is None or db_image.user_id != user.id):
        raise HTTPException(status_code=403, detail="没有删除此图片的权限")
    
    try:
        # 删除文件
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # 从数据库中删除记录
        db.delete(db_image)
        
        # 记录删除日志
        log_entry = UploadLog(
            filename=filename,
            original_filename=db_image.original_filename,
            mime_type=db_image.mime_type,
            size=db_image.size,
            status="deleted",
            ip_address=None,
            user_agent=None,
            user_id=user.id
        )
        db.add(log_entry)
        db.commit()
        
        # 更新Prometheus指标
        DELETE_COUNTER.inc()
        
        return {"message": "图片已删除"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除图片时出错: {str(e)}")

# 添加日志页面路由
@app.get("/logs/", response_class=HTMLResponse)
async def view_logs(
    request: Request,
    user: User = Depends(get_current_user),
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    # 只允许管理员访问
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="没有访问日志的权限")
    
    # 计算偏移量
    offset = (page - 1) * limit
    
    # 获取7天前的日期
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    # 查询日志条目
    total_logs = db.query(UploadLog).filter(UploadLog.upload_time >= seven_days_ago).count()
    logs = db.query(UploadLog).filter(UploadLog.upload_time >= seven_days_ago).order_by(
        UploadLog.upload_time.desc()
    ).offset(offset).limit(limit).all()
    
    # 计算总页数
    total_pages = (total_logs + limit - 1) // limit
    
    # 渲染模板
    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "logs": logs,
            "page": page,
            "total_pages": total_pages,
            "total_logs": total_logs,
            "limit": limit
        }
    )

# 添加Prometheus监控接口
@app.get("/metrics")
async def metrics(user: User = Depends(get_current_user)):
    # 只允许管理员访问
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="没有访问监控指标的权限")
    
    if not PROMETHEUS_ENABLED:
        return PlainTextResponse("监控指标未启用", media_type="text/plain")
    
    return PlainTextResponse(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 挂载上传目录
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 根路径路由
@app.get("/", tags=["系统"], summary="主页", description="PicUI图床服务主页")
async def home(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "current_user": current_user}
    )

# 管理面板路由
@app.get("/admin", tags=["系统"], summary="管理面板", description="PicUI管理面板")
async def admin_panel(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    # 如果用户未登录，重定向到登录页面
    if not current_user:
        return RedirectResponse(url="/login?next=/admin")
    
    # 渲染管理面板模板
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "user": current_user}
    )

# 登录页面
@app.get("/login", tags=["用户"], summary="登录页面", description="用户登录页面", response_class=HTMLResponse)
async def login_page(request: Request, next: str = ""):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "next": next}
    )

# 处理登录请求
@app.post("/login", tags=["用户"], summary="处理登录", description="处理用户登录请求")
async def login_handler(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
    db: Session = Depends(get_db)
):
    # 查找用户
    user = db.query(User).filter(User.username == username).first()
    
    # 验证用户和密码
    if not user or not user.check_password(password):
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "用户名或密码错误", "next": next}, 
            status_code=401
        )
    
    # 更新最后登录时间
    user.last_login = datetime.now()
    db.commit()
    
    # 创建会话
    session_id = secrets.token_hex(16)
    active_sessions[session_id] = {
        "user_id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "created_at": datetime.now()
    }
    
    # 设置Cookie
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=3600 * 24,  # 24小时
        httponly=True
    )
    
    # 重定向到下一个页面或默认到管理面板
    redirect_url = next if next else "/admin"
    return RedirectResponse(url=redirect_url, status_code=303)

# 获取带水印的图片
@app.get("/images/{filename}/watermark", tags=["图片"], summary="获取带水印的图片", description="获取添加水印后的图片")
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
    
    # 生成水印图片
    watermarked_img = add_watermark(file_path, text, position, opacity)
    if not watermarked_img:
        raise HTTPException(status_code=500, detail="添加水印失败")
    
    # 将图片转换为字节
    img_bytes = io.BytesIO()
    watermarked_img.save(img_bytes, format=watermarked_img.format or "JPEG")
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

# 短链接重定向
@app.get("/s/{code}", tags=["短链接"], summary="访问短链接", description="通过短链接代码访问图片")
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
@app.get("/images/{filename}", tags=["图片"], summary="查看图片", description="访问上传的图片")
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

# 创建临时外链
@app.post("/create-temp-link/{image_id}", tags=["短链接"], summary="创建临时外链", description="为图片创建带有有效期的临时外链")
async def create_temp_link(
    image_id: int,
    expire_minutes: int = Query(..., description="链接有效时间（分钟）", ge=1, le=10080),  # 最长7天
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 查询图片
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")
    
    # 检查权限，只有图片上传者和管理员可以创建临时链接
    if not current_user.is_admin and (image.user_id is None or image.user_id != current_user.id):
        raise HTTPException(status_code=403, detail="没有权限为此图片创建临时链接")
    
    # 创建临时短链接
    code = generate_short_link(
        filename=image.filename,
        user_id=current_user.id,
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

# 短链管理页面
@app.get("/admin/short-links", tags=["短链接"], summary="短链管理", description="管理短链接", response_class=HTMLResponse)
async def manage_short_links(
    request: Request,
    page: int = 1,
    limit: int = 20,
    search: str = "",
    session_data = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    # 计算偏移量
    offset = (page - 1) * limit
    
    # 构建查询
    query = db.query(ShortLink).join(
        Image, ShortLink.target_file == Image.filename, isouter=True
    )
    
    # 添加搜索条件
    if search:
        query = query.filter(
            ShortLink.code.contains(search) | 
            ShortLink.target_file.contains(search) |
            Image.original_filename.contains(search)
        )
    
    # 获取总数
    total = query.count()
    
    # 分页并获取结果
    short_links = query.order_by(ShortLink.created_at.desc()).offset(offset).limit(limit).all()
    
    # 计算总页数
    total_pages = (total + limit - 1) // limit
    
    # 渲染模板
    return templates.TemplateResponse(
        "short_links.html",
        {
            "request": request,
            "short_links": short_links,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "limit": limit,
            "search": search,
            "now": datetime.now()
        }
    )

# 删除短链接
@app.delete("/admin/short-links/{code}", tags=["短链接"], summary="删除短链接", description="删除短链接")
async def delete_short_link(
    code: str,
    session_data = Depends(verify_admin),
    db: Session = Depends(get_db)
):
    # 查询短链接
    short_link = db.query(ShortLink).filter(ShortLink.code == code).first()
    if not short_link:
        raise HTTPException(status_code=404, detail="短链接不存在")
    
    # 删除短链接
    db.delete(short_link)
    db.commit()
    
    return {"message": "短链接已删除"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True) 