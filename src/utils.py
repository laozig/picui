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
def optimize_image(img_path: str, max_size: int = 1920, max_dimension: int = 5000) -> bool:
    """
    优化图片：
    1. 限制最长边不超过max_size（默认1920px）
    2. 确保宽高不超过max_dimension（默认5000px）
    3. 保持原比例
    
    返回是否修改了图片
    """
    try:
        with PILImage.open(img_path) as img:
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
            img = img.resize((width, height), PILImage.LANCZOS)
            
            # 保存优化后的图片，保持原格式
            img.save(img_path, quality=90, optimize=True)
            return True
    except Exception as e:
        logger.error(f"图片优化失败: {str(e)}")
        return False

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
        # 打开原图片
        with PILImage.open(img_path) as img:
            # 创建一个透明的图层作为水印
            watermark = PILImage.new('RGBA', img.size, (0, 0, 0, 0))
            
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
            result = PILImage.alpha_composite(img, watermark)
            
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

# 检查磁盘空间利用率
def check_disk_usage(upload_dir: str, threshold: float = 80.0):
    """检查磁盘空间利用率，如果超过阈值则记录警告"""
    try:
        upload_path = os.path.abspath(upload_dir)
        
        # 获取目录所在分区的总空间和可用空间
        total, used, free = shutil.disk_usage(upload_path)
        
        # 计算利用率百分比
        usage_percent = (used / total) * 100
        
        logger.info(f"磁盘使用率检查: {usage_percent:.2f}% (总空间: {total/1024/1024/1024:.2f}GB, 已用: {used/1024/1024/1024:.2f}GB)")
        
        # 如果利用率超过阈值，记录警告
        if usage_percent > threshold:
            warning_msg = f"警告: 磁盘空间使用率已达 {usage_percent:.2f}%，超过设定阈值 {threshold}%"
            logger.warning(warning_msg)
        
        return usage_percent
    except Exception as e:
        logger.error(f"检查磁盘空间时出错: {str(e)}")
        return None 