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
    try:
        # 获取或创建会话
        _, user_id = get_or_create_session(request, response)
        logger.info(f"用户访问日志页面: user_id={user_id}")
        
        # 计算偏移量
        offset = (page - 1) * limit
        
        # 查询当前用户的日志总数 - 打印更详细的SQL查询信息
        user_id_condition = f"user_id = '{user_id}'"
        logger.info(f"查询条件: {user_id_condition}")
        
        # 查询所有日志，以决定是否应该显示所有日志而不是只显示当前用户的
        all_logs_count = db.query(func.count(UploadLog.id)).scalar()
        user_logs_count = db.query(func.count(UploadLog.id)).filter(UploadLog.user_id == user_id).scalar()
        
        # 获取一些示例日志，检查用户ID分布
        sample_logs = db.query(UploadLog).limit(5).all()
        user_ids = set()
        for log in sample_logs:
            if log.user_id:
                user_ids.add(log.user_id)
        
        logger.info(f"数据库中有 {all_logs_count} 条总日志，当前用户有 {user_logs_count} 条日志")
        logger.info(f"示例日志中的用户ID: {user_ids}")
        
        # 如果当前用户没有日志但数据库中有日志，则显示所有日志
        if user_logs_count == 0 and all_logs_count > 0:
            logger.info("当前用户没有日志，将显示所有日志")
            total_logs = all_logs_count
            logs = db.query(UploadLog).order_by(UploadLog.upload_time.desc()).offset(offset).limit(limit).all()
        else:
            # 正常情况，只显示当前用户的日志
            total_logs = user_logs_count
            logs = db.query(UploadLog).filter(UploadLog.user_id == user_id).order_by(UploadLog.upload_time.desc()).offset(offset).limit(limit).all()
        
        logger.info(f"最终查询结果: 找到 {len(logs)} 条日志记录")
        
        # 计算总页数
        total_pages = max(1, (total_logs + limit - 1) // limit)
        
        # 返回模板
        return templates.TemplateResponse(
            "logs.html",
            {
                "request": request,
                "logs": logs,
                "page": page,
                "total_pages": total_pages,
                "total_logs": total_logs,
                "limit": limit,
                "user_id": user_id  # 添加user_id到模板上下文中方便调试
            }
        )
    except Exception as e:
        logger.error(f"访问日志页面时出错: {str(e)}", exc_info=True)
        # 返回简单的错误页面
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>发生错误</title></head>
                <body>
                    <h1>访问出错</h1>
                    <p>系统在处理您的请求时遇到了问题。错误信息: {str(e)}</p>
                    <a href="/">返回主页</a>
                </body>
            </html>
            """,
            status_code=500
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
        logger.info(f"用户访问短链接管理页面: user_id={user_id}")
        
        # 计算偏移量
        offset = (page - 1) * limit
        
        # 查询所有短链接和当前用户的短链接
        all_links_count = db.query(func.count(ShortLink.code)).scalar()
        user_links_direct = db.query(func.count(ShortLink.code)).filter(ShortLink.user_id == user_id).scalar()
        
        # 查询与图片表关联的短链接
        user_links_joined = db.query(func.count(ShortLink.code)).join(
            Image, ShortLink.target_file == Image.filename
        ).filter(Image.user_id == user_id).scalar()
        
        logger.info(f"数据库中有 {all_links_count} 条总短链接，当前用户直接关联 {user_links_direct} 条，通过图片关联 {user_links_joined} 条")
        
        # 如果当前用户没有短链接但数据库中有短链接，则显示所有短链接
        if (user_links_direct == 0 and user_links_joined == 0) and all_links_count > 0:
            logger.info("当前用户没有短链接，将显示所有短链接")
            
            # 使用简单查询
            query = db.query(ShortLink)
            if search:
                query = query.filter(
                    ShortLink.code.contains(search) | 
                    ShortLink.target_file.contains(search)
                )
            
            total = query.count()
            short_links = query.order_by(ShortLink.created_at.desc()).offset(offset).limit(limit).all()
        else:
            # 如果join查询有结果，使用join查询
            if user_links_joined > 0:
                # 使用join查询
                query = db.query(ShortLink).join(
                    Image, ShortLink.target_file == Image.filename
                ).filter(Image.user_id == user_id)
                
                if search:
                    query = query.filter(
                        ShortLink.code.contains(search) | 
                        ShortLink.target_file.contains(search) |
                        Image.original_filename.contains(search)
                    )
                
                total = query.count()
                short_links = query.order_by(ShortLink.created_at.desc()).offset(offset).limit(limit).all()
            else:
                # 使用直接查询
                query = db.query(ShortLink).filter(ShortLink.user_id == user_id)
                if search:
                    query = query.filter(
                        ShortLink.code.contains(search) | 
                        ShortLink.target_file.contains(search)
                    )
                
                total = query.count()
                short_links = query.order_by(ShortLink.created_at.desc()).offset(offset).limit(limit).all()
        
        logger.info(f"最终查询结果: 找到 {len(short_links)} 条短链接记录")
        
        # 计算总页数
        total_pages = max(1, (total + limit - 1) // limit)
        
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

# 删除短链接
@router.delete("/admin/short-links/{code}", tags=["页面"], summary="删除短链接", description="删除指定的短链接")
async def delete_short_link(
    code: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """删除指定的短链接"""
    logger.info(f"接收到删除短链接请求: code={code}")
    try:
        # 获取用户ID
        user_id = get_user_id(request)
        if not user_id:
            logger.warning("删除短链接失败: 用户未登录")
            return {"success": False, "message": "用户未登录"}
        
        # 查询短链接
        short_link = db.query(ShortLink).filter(ShortLink.code == code).first()
        if not short_link:
            logger.warning(f"删除短链接失败: 短链接不存在, code={code}")
            return {"success": False, "message": "短链接不存在"}
        
        # 检查权限（验证是否是该用户创建的短链接）
        # 查找关联的图片
        image = db.query(Image).filter(Image.filename == short_link.target_file).first()
        if image and image.user_id != user_id:
            logger.warning(f"用户({user_id})尝试删除其他用户({image.user_id})的短链接: {code}")
            return {"success": False, "message": "无权删除其他用户的短链接"}
        
        # 删除短链接
        db.delete(short_link)
        db.commit()
        logger.info(f"短链接已删除: code={code}, user_id={user_id}")
        
        return {"success": True, "message": "短链接已成功删除"}
    except Exception as e:
        logger.error(f"删除短链接时出错: {str(e)}", exc_info=True)
        db.rollback()
        return {"success": False, "message": f"删除短链接时出错: {str(e)}"}

# 删除了测试页面路由 