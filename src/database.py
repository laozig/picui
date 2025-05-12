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
        
        logger.info(f"尝试连接数据库文件: {db_path}")
        
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 记录已添加的列
        added_columns = []
        
        # 检查images表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images';")
        if not cursor.fetchone():
            # images表不存在，创建表
            logger.info("images表不存在，创建新表")
            cursor.execute("""
                CREATE TABLE images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT UNIQUE,
                    original_filename TEXT,
                    file_size FLOAT,
                    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    upload_ip TEXT,
                    user_id TEXT,
                    mime_type TEXT DEFAULT 'image/jpeg',
                    width INTEGER,
                    height INTEGER,
                    description TEXT
                )
            """)
            cursor.execute("CREATE INDEX idx_images_filename ON images(filename);")
            cursor.execute("CREATE INDEX idx_images_user_id ON images(user_id);")
            added_columns.append("创建images表")
        else:
            # 获取images表的列信息
            cursor.execute("PRAGMA table_info(images);")
            existing_columns = [column[1] for column in cursor.fetchall()]
            
            # 需要检查的列
            columns_to_check = {
                "upload_ip": "TEXT",
                "file_size": "FLOAT",
                "width": "INTEGER",
                "height": "INTEGER",
                "description": "TEXT",
                "user_id": "TEXT",
                "mime_type": "TEXT DEFAULT 'image/jpeg'"
            }
            
            # 检查并添加缺失的列
            for col_name, col_type in columns_to_check.items():
                if col_name not in existing_columns:
                    try:
                        sql = f"ALTER TABLE images ADD COLUMN {col_name} {col_type};"
                        cursor.execute(sql)
                        added_columns.append(f"images.{col_name}")
                        logger.info(f"成功添加 {col_name} 列到 images 表")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" not in str(e).lower():
                            logger.warning(f"无法添加 {col_name} 列到 images 表: {str(e)}")
        
        # 检查short_links表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='short_links';")
        if not cursor.fetchone():
            # short_links表不存在，创建表
            logger.info("short_links表不存在，创建新表")
            cursor.execute("""
                CREATE TABLE short_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE,
                    target_file TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    expire_at TIMESTAMP,
                    is_enabled BOOLEAN DEFAULT 1,
                    user_id TEXT
                )
            """)
            cursor.execute("CREATE INDEX idx_short_links_code ON short_links(code);")
            cursor.execute("CREATE INDEX idx_short_links_target_file ON short_links(target_file);")
            cursor.execute("CREATE INDEX idx_short_links_user_id ON short_links(user_id);")
            added_columns.append("创建short_links表")
        else:
            # 获取short_links表的列信息
            cursor.execute("PRAGMA table_info(short_links);")
            existing_columns = [column[1] for column in cursor.fetchall()]
            
            # 需要检查的列
            columns_to_check = {
                "is_enabled": "BOOLEAN DEFAULT 1",
                "user_id": "TEXT",
                "access_count": "INTEGER DEFAULT 0",
                "expire_at": "TIMESTAMP"
            }
            
            # 检查并添加缺失的列
            for col_name, col_type in columns_to_check.items():
                if col_name not in existing_columns:
                    try:
                        sql = f"ALTER TABLE short_links ADD COLUMN {col_name} {col_type};"
                        cursor.execute(sql)
                        added_columns.append(f"short_links.{col_name}")
                        logger.info(f"成功添加 {col_name} 列到 short_links 表")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" not in str(e).lower():
                            logger.warning(f"无法添加 {col_name} 列到 short_links 表: {str(e)}")
        
        # 检查upload_logs表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='upload_logs';")
        if not cursor.fetchone():
            # upload_logs表不存在，创建表
            logger.info("upload_logs表不存在，创建新表")
            cursor.execute("""
                CREATE TABLE upload_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_filename TEXT,
                    saved_filename TEXT,
                    status TEXT,
                    file_size FLOAT,
                    error_message TEXT,
                    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT,
                    user_id TEXT
                )
            """)
            cursor.execute("CREATE INDEX idx_upload_logs_user_id ON upload_logs(user_id);")
            added_columns.append("创建upload_logs表")
        else:
            # 获取upload_logs表的列信息
            cursor.execute("PRAGMA table_info(upload_logs);")
            existing_columns = [column[1] for column in cursor.fetchall()]
            
            # 需要检查的列
            columns_to_check = {
                "saved_filename": "TEXT",
                "file_size": "FLOAT",
                "user_id": "TEXT",
                "user_agent": "TEXT"
            }
            
            # 检查并添加缺失的列
            for col_name, col_type in columns_to_check.items():
                if col_name not in existing_columns:
                    try:
                        sql = f"ALTER TABLE upload_logs ADD COLUMN {col_name} {col_type};"
                        cursor.execute(sql)
                        added_columns.append(f"upload_logs.{col_name}")
                        logger.info(f"成功添加 {col_name} 列到 upload_logs 表")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" not in str(e).lower():
                            logger.warning(f"无法添加 {col_name} 列到 upload_logs 表: {str(e)}")
        
        # 提交所有更改
        conn.commit()
        
        # 添加详细日志信息
        if added_columns:
            logger.info(f"数据库升级完成，添加了以下列: {', '.join(added_columns)}")
        else:
            logger.info("数据库结构已是最新，无需升级")
        
        # 关闭连接
        conn.close()
        
    except Exception as e:
        logger.error(f"数据库升级失败: {str(e)}", exc_info=True)
        raise

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