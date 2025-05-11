from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from datetime import datetime

from src.database import get_db, ShortLink, UploadLog, Image

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
async def home(request: Request):
    """渲染主页模板"""
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# 查看上传日志页面
@router.get("/logs/", response_class=HTMLResponse, tags=["页面"], summary="上传日志", description="查看上传日志页面")
async def view_logs(
    request: Request,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """渲染上传日志页面"""
    # 计算偏移量
    offset = (page - 1) * limit
    
    # 查询日志总数
    total_logs = db.query(func.count(UploadLog.id)).scalar()
    
    # 分页查询日志
    logs = db.query(UploadLog).order_by(UploadLog.upload_time.desc()).offset(offset).limit(limit).all()
    
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
async def admin_panel(request: Request):
    """渲染管理面板模板"""
    return templates.TemplateResponse(
        "admin.html",
        {"request": request}
    )

# 短链管理页面
@router.get("/admin/short-links", tags=["页面"], summary="短链管理", description="管理短链接", response_class=HTMLResponse)
async def manage_short_links(
    request: Request,
    page: int = 1,
    limit: int = 20,
    search: str = "",
    db: Session = Depends(get_db)
):
    """渲染短链接管理页面"""
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