from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
import datetime
import os
import secrets
import string
import random

# 数据库配置
# 默认使用SQLite，但也可以通过环境变量使用其他数据库
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./picui.db")

# 创建数据库引擎
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(DATABASE_URL)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建Base类
Base = declarative_base()

# 定义图片模型
class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    original_filename = Column(String)
    file_size = Column(Float)  # 单位：KB
    upload_time = Column(DateTime, default=func.now())
    upload_ip = Column(String)
    user_id = Column(String, index=True, nullable=True)  # 添加用户ID字段
    mime_type = Column(String, default="image/jpeg")  # MIME类型
    width = Column(Integer, nullable=True)  # 图片宽度
    height = Column(Integer, nullable=True)  # 图片高度
    description = Column(Text, nullable=True)  # 图片描述
    
    def __repr__(self):
        return f"<Image {self.filename}>"

# 定义上传日志模型
class UploadLog(Base):
    __tablename__ = "upload_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String)
    saved_filename = Column(String, nullable=True)
    status = Column(String)  # success, failed
    file_size = Column(Float, nullable=True)  # 单位：KB
    error_message = Column(Text, nullable=True)
    upload_time = Column(DateTime, default=func.now())
    ip_address = Column(String)
    user_agent = Column(String, nullable=True)
    user_id = Column(String, index=True, nullable=True)  # 添加用户ID字段
    
    def __repr__(self):
        return f"<UploadLog {self.original_filename} - {self.status}>"

# 定义短链接模型
class ShortLink(Base):
    __tablename__ = "short_links"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)  # 短链接编码，例如 abc123
    target_file = Column(String, index=True)  # 指向的原始图片文件名
    created_at = Column(DateTime, default=func.now())
    access_count = Column(Integer, default=0)  # 访问计数
    expire_at = Column(DateTime, nullable=True)  # 过期时间，为null则永不过期
    is_enabled = Column(Boolean, default=True)
    user_id = Column(String, index=True, nullable=True)  # 添加用户ID字段
    
    def is_expired(self):
        """检查链接是否已过期"""
        if self.expire_at is None:
            return False
        return datetime.datetime.utcnow() > self.expire_at
    
    def increase_access_count(self):
        """增加访问计数"""
        self.access_count += 1
    
    @staticmethod
    def generate_code(length=6):
        """生成随机短链接编码"""
        chars = string.ascii_lowercase + string.ascii_uppercase + string.digits
        return ''.join(random.choice(chars) for _ in range(length))
    
    def __repr__(self):
        return f"<ShortLink {self.code} -> {self.target_file}>"

# 创建数据库表
def create_tables():
    Base.metadata.create_all(bind=engine)

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 如果数据库文件不存在，则创建表
if not os.path.exists("picui.db"):
    create_tables() 