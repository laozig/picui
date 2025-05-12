import os
import time
import shutil
import logging
import asyncio
from datetime import datetime, timedelta
import numpy as np
import base64
import io
import hmac
import hashlib
import uuid
import requests
import json
import threading
from typing import Set, Optional
from PIL import Image as PILImage

logger = logging.getLogger("picui")

# 允许的图片格式
ALLOWED_EXTENSIONS = {
    "jpg", "jpeg", "png", "gif", "webp", 
    "bmp", "tiff", "tif", "svg", "ico", 
    "heic", "heif", "avif", "jfif", "pjpeg", "pjp"
}

# 检查文件格式是否允许
def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否在允许列表中"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 优化图片尺寸
def optimize_image(input_path: str) -> str:
    """
    优化图片尺寸，减小文件大小
    
    返回优化结果描述字符串
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(input_path):
            logger.error(f"优化图片失败: 文件不存在 {input_path}")
            return ""

        # 获取文件后缀
        _, ext = os.path.splitext(input_path)
        ext = ext.lower()

        # 检查是否是SVG文件，如果是则不进行优化
        if ext == '.svg':
            return "(SVG跳过优化)"

        # 检查图片库
        try:
            from PIL import Image
        except ImportError:
            logger.warning("PIL库未安装，跳过图片优化")
            return "(PIL缺失)"

        # 打开图片
        with Image.open(input_path) as img:
            # 获取原始尺寸
            orig_width, orig_height = img.size
            
            # 检查图片尺寸是否超过限制
            MAX_WIDTH = 1920
            MAX_HEIGHT = 1920
            
            # 如果图片尺寸在范围内，不进行优化
            if orig_width <= MAX_WIDTH and orig_height <= MAX_HEIGHT:
                return f"({orig_width}x{orig_height})"
            
            # 计算等比例缩放后的尺寸
            ratio = min(MAX_WIDTH / orig_width, MAX_HEIGHT / orig_height)
            new_width = int(orig_width * ratio)
            new_height = int(orig_height * ratio)
            
            # 缩放图片
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 保存图片
            img_resized.save(input_path, quality=95, optimize=True)
            
            return f"({orig_width}x{orig_height} → {new_width}x{new_height})"
    except Exception as e:
        logger.error(f"优化图片失败: {str(e)}")
        return f"(优化出错: {str(e)[:20]}...)"

# 添加水印
def add_watermark(img_path: str, text: str, position: str = "center", 
                 opacity: float = 0.5, output_path: Optional[str] = None):
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
        logger.info(f"开始添加水印: 文件={img_path}, 文字='{text}', 位置={position}, 不透明度={opacity}")
        
        # 打开原图片
        img = PILImage.open(img_path)
        original_mode = img.mode
        original_format = img.format
        logger.info(f"原始图片信息: 尺寸={img.size}, 模式={original_mode}, 格式={original_format}")
        
        # 优化内存使用 - 处理大图像时先缩小
        if img.width > 3000 or img.height > 3000:
            img = img.copy()  # 创建副本避免修改原图
            img.thumbnail((3000, 3000), PILImage.LANCZOS)
            logger.info(f"图像过大，已缩小到 {img.size}")
        
        # 保存格式信息到图片对象，以便后续使用
        if not hasattr(img, 'format') or not img.format:
            # 从文件扩展名猜测格式
            ext = os.path.splitext(img_path)[1].lower()
            if ext == '.jpg' or ext == '.jpeg':
                img.format = 'JPEG'
            elif ext == '.png':
                img.format = 'PNG'
            elif ext == '.gif':
                img.format = 'GIF'
            elif ext == '.webp':
                img.format = 'WEBP'
            else:
                img.format = 'JPEG'  # 默认用JPEG
            logger.info(f"从文件名推断格式: {img.format}")
        
        # 创建一个透明的图层作为水印
        try:
            watermark = PILImage.new('RGBA', img.size, (0, 0, 0, 0))
            
            # 创建绘图对象
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(watermark)
            
            # 尝试加载系统字体
            font = None
            try:
                # 对于Windows系统
                font = ImageFont.truetype('arial.ttf', size=int(min(img.size) / 20))
                logger.info(f"使用Windows系统字体: arial.ttf")
            except Exception as e:
                logger.warning(f"加载Windows字体失败: {str(e)}")
                try:
                    # 对于Linux系统
                    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', size=int(min(img.size) / 20))
                    logger.info(f"使用Linux系统字体: DejaVuSans.ttf")
                except Exception as e:
                    logger.warning(f"加载Linux字体失败: {str(e)}")
                    # 降级到默认字体
                    font = ImageFont.load_default()
                    logger.info(f"使用默认字体")
            
            # 获取文本大小 - 使用textbbox或fallback到textsize
            try:
                # 新版Pillow使用textbbox
                left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
                text_width = right - left
                text_height = bottom - top
                logger.info(f"使用textbbox获取文本尺寸: 宽={text_width}, 高={text_height}")
            except AttributeError as e:
                logger.warning(f"textbbox不可用: {str(e)}")
                # 旧版Pillow使用textsize
                text_width, text_height = draw.textsize(text, font=font)
                logger.info(f"使用textsize获取文本尺寸: 宽={text_width}, 高={text_height}")
            
            # 根据position确定水印位置
            if position == "center":
                pos = ((img.size[0] - text_width) / 2, (img.size[1] - text_height) / 2)
            elif position == "bottom-right":
                pos = (img.size[0] - text_width - 20, img.size[1] - text_height - 20)
            elif position == "bottom-left":
                pos = (20, img.size[1] - text_height - 20)
            elif position == "top-right":
                pos = (img.size[0] - text_width - 20, 20)
            elif position == "top-left":
                pos = (20, 20)
            else:
                # 默认使用右下角
                pos = (img.size[0] - text_width - 20, img.size[1] - text_height - 20)
                logger.warning(f"未知的位置值: {position}，默认使用右下角")
            
            logger.info(f"水印位置: {pos}")
            
            # 绘制水印文字，半透明黑色背景
            padding = 10
            draw.rectangle(
                [
                    pos[0] - padding, 
                    pos[1] - padding, 
                    pos[0] + text_width + padding, 
                    pos[1] + text_height + padding
                ], 
                fill=(0, 0, 0, int(128 * opacity))
            )
            
            # 绘制水印文字，白色
            draw.text(pos, text, font=font, fill=(255, 255, 255, int(255 * opacity)))
            
            # 转换图片模式处理
            result = None
            
            if original_mode == 'RGBA':
                # 如果原图已经是RGBA，直接合成
                result = PILImage.alpha_composite(img, watermark)
            else:
                # 尝试转换为RGBA再合成
                try:
                    img_rgba = img.convert('RGBA')
                    result = PILImage.alpha_composite(img_rgba, watermark)
                    # 转回原来的模式
                    result = result.convert(original_mode)
                except Exception as e:
                    logger.error(f"图片模式转换失败: {str(e)}")
                    # 如果转换失败，使用原始图片
                    result = img.copy()
            
            # 保存原始格式信息
            if original_format:
                result.format = original_format
            
            logger.info(f"✓ 水印添加完成: 结果图片尺寸={result.size}, 模式={result.mode}, 格式={result.format}")
            
            # 如果指定了输出路径，则保存图片
            if output_path:
                logger.info(f"保存水印图片到: {output_path}")
                if result.format == 'JPEG':
                    result.save(output_path, format=result.format, quality=95)
                else:
                    result.save(output_path, format=result.format)
                logger.info(f"✓ 水印图片已保存")
                return True
            else:
                return result
                
        except Exception as inner_e:
            logger.error(f"处理水印图层时出错: {str(inner_e)}", exc_info=True)
            # 如果水印处理出错，返回原始图片作为后备方案
            logger.warning(f"返回原始图片作为后备方案")
            return img
    except Exception as e:
        logger.error(f"添加水印失败: {str(e)}", exc_info=True)
        if output_path:
            return False
        # 尝试返回原图作为后备方案
        try:
            return PILImage.open(img_path)
        except:
            return None

# 简单的离线图片内容检测
def offline_image_check(file_path: str, skin_threshold: float = 0.5) -> bool:
    """
    简单的离线图片检测函数，主要检测肤色比例
    返回True表示安全，False表示不安全

    注意: 这是一个非常基础的检测方法，不能替代专业的内容审核服务
    """
    try:
        # 打开图片
        img = PILImage.open(file_path)
        
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
        if skin_ratio > skin_threshold:
            logger.warning(f"离线检测: 图片 {file_path} 可能包含不适当内容 (肤色比例: {skin_ratio:.2f})")
            return False
            
        return True
    except Exception as e:
        logger.error(f"离线图片检测出错: {str(e)}")
        return True  # 出错时默认通过

# 检查磁盘空间使用情况
def check_disk_usage(path=None, threshold=80.0):
    """
    检查指定路径的磁盘空间使用情况
    
    当剩余空间低于阈值时，将发出警告
    
    参数:
    - path: 要检查的路径，默认为当前目录
    - threshold: 磁盘使用率阈值（百分比），超过此值将发出警告
    """
    # 如果未指定路径，使用当前目录
    if path is None:
        path = os.getcwd()
    
    # 确保路径存在
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    
    # 获取磁盘使用情况
    try:
        if hasattr(os, 'statvfs'):  # Unix/Linux/MacOS
            stat = os.statvfs(path)
            free = stat.f_bavail * stat.f_frsize
            total = stat.f_blocks * stat.f_frsize
            used = (stat.f_blocks - stat.f_bfree) * stat.f_frsize
        else:  # Windows
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            total_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(path), None, ctypes.pointer(total_bytes), ctypes.pointer(free_bytes)
            )
            total = total_bytes.value
            free = free_bytes.value
            used = total - free
        
        # 计算使用率
        used_percent = (used / total) * 100
        
        # 转换为可读格式
        total_gb = total / (1024 * 1024 * 1024)
        used_gb = used / (1024 * 1024 * 1024)
        free_gb = free / (1024 * 1024 * 1024)
        
        # 检查是否超过阈值
        if used_percent > threshold:
            logger.warning(f"磁盘空间不足，利用率已达 {used_percent:.1f}%。剩余: {free_gb:.2f} GB")
        else:
            # 使用debug级别记录正常情况
            logger.debug(f"磁盘空间正常: 利用率 {used_percent:.1f}%，总容量: {total_gb:.2f} GB，已用: {used_gb:.2f} GB，剩余: {free_gb:.2f} GB")
        
        return used_percent
    except Exception as e:
        logger.error(f"检查磁盘空间出错: {str(e)}")
        return None 