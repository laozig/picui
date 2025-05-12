import secrets
import time
import logging
from typing import Dict, Optional, Tuple
from fastapi import Request, Response
import uuid

# 配置日志
logger = logging.getLogger("picui")

# 会话存储
sessions: Dict[str, Dict] = {}

# 用户ID到会话ID的映射
user_sessions: Dict[str, str] = {}

# 会话过期时间（秒）
SESSION_EXPIRE = 30 * 24 * 60 * 60  # 30天

# 会话Cookie名称
COOKIE_NAME = "picui_session"

def generate_session_id() -> str:
    """生成唯一的会话ID"""
    return secrets.token_urlsafe(32)

def generate_user_id() -> str:
    """生成唯一的用户ID"""
    return str(uuid.uuid4())

def create_session(response: Response, ip_address: str) -> Tuple[str, str]:
    """
    创建新会话，设置Cookie，并返回会话ID和用户ID
    
    Args:
        response: FastAPI响应对象，用于设置Cookie
        ip_address: 用户IP地址（用于记录）
    
    Returns:
        Tuple[str, str]: 会话ID和用户ID
    """
    session_id = generate_session_id()
    user_id = generate_user_id()
    
    # 创建会话数据
    sessions[session_id] = {
        "user_id": user_id,
        "created_at": time.time(),
        "last_accessed": time.time(),
        "ip_address": ip_address
    }
    
    # 建立用户ID到会话ID的映射
    user_sessions[user_id] = session_id
    
    # 设置Cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        max_age=SESSION_EXPIRE,
        httponly=True,
        samesite="lax"
    )
    
    logger.info(f"已创建新会话: session_id={session_id}, user_id={user_id}")
    return session_id, user_id

def get_or_create_session(request: Request, response: Response) -> Tuple[str, str]:
    """
    获取现有会话或创建新会话
    
    Args:
        request: FastAPI请求对象
        response: FastAPI响应对象
    
    Returns:
        Tuple[str, str]: 会话ID和用户ID
    """
    try:
        # 尝试从Cookie获取会话ID
        session_id = request.cookies.get(COOKIE_NAME)
        
        # 获取客户端IP
        ip_address = request.client.host
        
        # 如果会话ID存在且有效
        if session_id and session_id in sessions:
            # 更新最后访问时间
            sessions[session_id]["last_accessed"] = time.time()
            user_id = sessions[session_id]["user_id"]
            return session_id, user_id
        
        # 创建新会话
        return create_session(response, ip_address)
    except Exception as e:
        logger.error(f"会话处理出错: {str(e)}", exc_info=True)
        # 出错时创建临时会话，不设置Cookie
        temp_session_id = generate_session_id()
        temp_user_id = generate_user_id()
        return temp_session_id, temp_user_id

def get_user_id(request: Request) -> Optional[str]:
    """
    从请求中获取用户ID
    
    Args:
        request: FastAPI请求对象
    
    Returns:
        Optional[str]: 用户ID，如果会话无效则返回None
    """
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id or session_id not in sessions:
        return None
    
    return sessions[session_id]["user_id"]

def clean_expired_sessions():
    """清理过期的会话"""
    current_time = time.time()
    expired_sessions = []
    
    # 找出过期的会话
    for session_id, data in sessions.items():
        if current_time - data["last_accessed"] > SESSION_EXPIRE:
            expired_sessions.append(session_id)
    
    # 删除过期的会话和对应的用户映射
    for session_id in expired_sessions:
        user_id = sessions[session_id]["user_id"]
        if user_id in user_sessions:
            del user_sessions[user_id]
        del sessions[session_id]
    
    if expired_sessions:
        logger.info(f"已清理 {len(expired_sessions)} 个过期会话") 