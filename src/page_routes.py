from fastapi import APIRouter, Depends, Request, Response, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from datetime import datetime
import logging

from src.database import get_db, ShortLink, UploadLog, Image
from src.session import get_or_create_session, get_user_id

# 配置日志
logger = logging.getLogger("picui")

# 创建路由器
router = APIRouter()

# 全局模板变量
templates = None

def set_templates(template_instance):
    """设置模板实例"""
    global templates
    templates = template_instance

# 主页路由
@router.get("/", tags=["页面"], summary="主页", description="PicUI图床服务主页")
async def home(request: Request, response: Response):
    """渲染主页模板，同时确保用户有会话Cookie"""
    try:
        # 获取或创建会话
        _, user_id = get_or_create_session(request, response)
        logger.info(f"用户访问主页: user_id={user_id}")
        
        return templates.TemplateResponse(
            "index.html",
            {"request": request}
        )
    except Exception as e:
        logger.error(f"主页访问出错: {str(e)}", exc_info=True)
        # 返回简单的错误页面
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>发生错误</title></head>
                <body>
                    <h1>访问出错</h1>
                    <p>系统在处理您的请求时遇到了问题。错误信息: {str(e)}</p>
                    <a href="/">刷新重试</a>
                </body>
            </html>
            """,
            status_code=500
        )

# 查看上传日志页面
@router.get("/logs/", response_class=HTMLResponse, tags=["页面"], summary="上传日志", description="查看上传日志页面")
async def view_logs(
    request: Request,
    response: Response,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """渲染上传日志页面"""
    # 获取或创建会话
    _, user_id = get_or_create_session(request, response)
    
    # 计算偏移量
    offset = (page - 1) * limit
    
    # 查询当前用户的日志总数
    total_logs = db.query(func.count(UploadLog.id)).filter(UploadLog.user_id == user_id).scalar()
    
    # 分页查询当前用户的日志
    logs = db.query(UploadLog).filter(UploadLog.user_id == user_id).order_by(UploadLog.upload_time.desc()).offset(offset).limit(limit).all()
    
    # 计算总页数
    total_pages = (total_logs + limit - 1) // limit
    
    # 返回模板
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

# 管理面板路由
@router.get("/admin", tags=["页面"], summary="管理面板", description="PicUI管理面板")
async def admin_panel(request: Request, response: Response):
    """渲染管理面板模板"""
    # 获取或创建会话
    get_or_create_session(request, response)
    
    return templates.TemplateResponse(
        "admin.html",
        {"request": request}
    )

# 短链管理页面
@router.get("/admin/short-links", tags=["页面"], summary="短链管理", description="管理短链接", response_class=HTMLResponse)
async def manage_short_links(
    request: Request,
    response: Response,
    page: int = 1,
    limit: int = 20,
    search: str = "",
    db: Session = Depends(get_db)
):
    """渲染短链接管理页面"""
    try:
        # 获取或创建会话
        _, user_id = get_or_create_session(request, response)
        
        # 计算偏移量
        offset = (page - 1) * limit
        
        # 构建查询 - 只查询当前用户上传的图片相关的短链接
        query = db.query(ShortLink).join(
            Image, ShortLink.target_file == Image.filename
        ).filter(Image.user_id == user_id)
        
        # 添加搜索条件
        if search:
            query = query.filter(
                ShortLink.code.contains(search) | 
                ShortLink.target_file.contains(search) |
                Image.original_filename.contains(search)
            )
        
        try:
            # 获取总数
            total = query.count()
            
            # 分页并获取结果
            short_links = query.order_by(ShortLink.created_at.desc()).offset(offset).limit(limit).all()
            
            # 计算总页数
            total_pages = (total + limit - 1) // limit
        except Exception as db_error:
            logger.error(f"查询短链接数据时出错: {str(db_error)}", exc_info=True)
            # 如果发生错误，使用空数据
            short_links = []
            total = 0
            total_pages = 1
        
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
                "now": datetime.now(),
                "max": max,  # 提供内置的max函数
                "min": min   # 提供内置的min函数
            }
        )
    except Exception as e:
        logger.error(f"短链接管理页面访问出错: {str(e)}", exc_info=True)
        # 返回简单的错误页面
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>发生错误</title></head>
                <body>
                    <h1>访问出错</h1>
                    <p>系统在处理您的请求时遇到了问题。错误信息: {str(e)}</p>
                    <a href="/admin">返回管理面板</a>
                </body>
            </html>
            """,
            status_code=500
        )

# 删除了测试页面路由 