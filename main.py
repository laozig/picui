from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import shutil
import os
from typing import List
import uuid
from sqlalchemy.orm import Session
import mimetypes

from database import get_db, create_tables, Image

# 获取环境变量
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")

app = FastAPI(title="图床服务")

# 确保上传目录存在
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 允许的图片格式
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}

# 文件大小限制 (5MB)
MAX_SIZE = int(os.getenv("MAX_FILE_SIZE", 5 * 1024 * 1024))  # 默认5MB

# 在应用启动时创建数据库表
@app.on_event("startup")
def startup_event():
    create_tables()

# 检查文件格式是否允许
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.post("/upload")
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db), request: Request = None):
    # 检查文件类型
    if not allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail="只允许上传 jpg, jpeg, png, gif, webp 格式的图片"
        )
    
    # 读取文件内容
    contents = await file.read()
    
    # 检查文件大小
    if len(contents) > MAX_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小不能超过{MAX_SIZE/1024/1024:.0f}MB"
        )
    
    # 重置文件指针
    await file.seek(0)
    
    # 生成唯一文件名
    file_extension = file.filename.split('.')[-1]
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    file_location = os.path.join(UPLOAD_DIR, unique_filename)
    
    # 保存文件
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
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
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    
    # 动态生成URL
    if request:
        # 如果请求可用，从请求中构建URL
        host = request.headers.get("host", "localhost")
        scheme = request.headers.get("x-forwarded-proto", "http")
        base_url = f"{scheme}://{host}"
        file_url = f"{base_url}/images/{unique_filename}"
    else:
        # 如果不可用，使用配置的BASE_URL
        file_url = f"{BASE_URL}/images/{unique_filename}"
    
    return {"url": file_url, "filename": unique_filename, "id": db_image.id}

@app.get("/images/{filename}")
async def get_image(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(file_path)

@app.get("/images")
def list_images(db: Session = Depends(get_db), skip: int = 0, limit: int = 100):
    images = db.query(Image).offset(skip).limit(limit).all()
    return images

# 根路径重定向到前端页面
@app.get("/")
async def root():
    return FileResponse("static/index.html")

# 添加健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 挂载上传目录
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True) 