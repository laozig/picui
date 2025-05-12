from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
import datetime
import os
import secrets
import string
import random
import logging
import sqlite3

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
    file_size = Column(Float, nullable=True)  # 单位：KB，允许为空
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
    is_enabled = Column(Boolean, default=True, nullable=True)  # 设置默认值为True，允许为空
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
    """创建或更新数据库表结构
    
    会根据模型定义创建表，如果表不存在则会安全地更新表结构
    """
    logger = logging.getLogger("picui")
    
    try:
        # 安全地创建表，如果表不存在
        Base.metadata.create_all(bind=engine)
        logger.info("✓ 数据库表结构已创建或更新")
    except Exception as e:
        logger.error(f"数据库表结构创建失败: {str(e)}", exc_info=True)
        raise

# 升级数据库结构，添加缺失的列
def upgrade_database():
    """升级数据库表结构，添加缺失的列"""
    logger = logging.getLogger("picui")
    
    try:
        # 从DATABASE_URL中提取数据库文件路径
        db_path = "picui.db"
        if DATABASE_URL.startswith("sqlite:///"):
            db_path = DATABASE_URL.replace("sqlite:///", "").replace("./", "")
        
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 记录已添加的列
        added_columns = []
        
        # 尝试添加upload_ip列到images表
        try:
            cursor.execute("ALTER TABLE images ADD COLUMN upload_ip TEXT;")
            added_columns.append("images.upload_ip")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                logger.debug(f"无法添加 upload_ip 列到 images 表: {str(e)}")
                
        # 尝试添加file_size列到images表
        try:
            cursor.execute("ALTER TABLE images ADD COLUMN file_size FLOAT;")
            added_columns.append("images.file_size")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                logger.debug(f"无法添加 file_size 列到 images 表: {str(e)}")
        
        # 尝试添加is_enabled列到short_links表
        try:
            cursor.execute("ALTER TABLE short_links ADD COLUMN is_enabled BOOLEAN DEFAULT 1;")
            added_columns.append("short_links.is_enabled")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                logger.debug(f"无法添加 is_enabled 列到 short_links 表: {str(e)}")
        
        # 尝试添加saved_filename列到upload_logs表
        try:
            cursor.execute("ALTER TABLE upload_logs ADD COLUMN saved_filename TEXT;")
            added_columns.append("upload_logs.saved_filename")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                logger.debug(f"无法添加 saved_filename 列到 upload_logs 表: {str(e)}")
        
        # 尝试添加file_size列到upload_logs表
        try:
            cursor.execute("ALTER TABLE upload_logs ADD COLUMN file_size FLOAT;")
            added_columns.append("upload_logs.file_size")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                logger.debug(f"无法添加 file_size 列到 upload_logs 表: {str(e)}")
        
        # 提交更改
        conn.commit()
        conn.close()
        
        # 只在有新增列时输出日志
        if added_columns:
            logger.info(f"✓ 数据库升级完成，已添加列: {', '.join(added_columns)}")
        else:
            logger.debug("✓ 数据库升级完成，未添加新列")
            
        return True
    except Exception as e:
        logger.error(f"数据库升级失败: {str(e)}")
        return False

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
# 尝试升级数据库结构
else:
    upgrade_database() 