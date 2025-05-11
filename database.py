from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import os
import secrets
import hashlib
import bcrypt
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

# 定义用户模型
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    is_admin = Column(Boolean, default=False)
    api_token = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    totp_secret = Column(String, nullable=True)
    totp_enabled = Column(Boolean, default=False)
    
    # 关系
    images = relationship("Image", back_populates="user")
    
    def __init__(self, username, email, password, is_admin=False):
        self.username = username
        self.email = email
        self.set_password(password)
        self.is_admin = is_admin
        self.generate_api_token()
        self.totp_enabled = False
    
    def set_password(self, password):
        """设置密码哈希"""
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    
    def check_password(self, password):
        """验证密码"""
        password_bytes = password.encode('utf-8')
        stored_hash = self.password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, stored_hash)
    
    def generate_api_token(self):
        """生成API令牌"""
        self.api_token = secrets.token_hex(16)
        return self.api_token
    
    def __repr__(self):
        return f"<User {self.username}>"

# 定义图片模型
class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True)
    original_filename = Column(String)
    size = Column(Float)  # 以KB为单位
    mime_type = Column(String)
    upload_time = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # 关系
    user = relationship("User", back_populates="images")
    
    def __repr__(self):
        return f"<Image {self.filename}>"

# 定义上传日志模型
class UploadLog(Base):
    __tablename__ = "upload_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    original_filename = Column(String)
    size = Column(Float)  # 以KB为单位
    mime_type = Column(String)
    upload_time = Column(DateTime, default=datetime.datetime.utcnow)
    ip_address = Column(String)
    user_agent = Column(String)
    status = Column(String)  # 成功、失败或删除
    error_message = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # 关系
    user = relationship("User")
    
    def __repr__(self):
        return f"<UploadLog {self.filename} - {self.status}>"

# 定义短链接模型
class ShortLink(Base):
    __tablename__ = "short_links"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)  # 短链接编码，例如 abc123
    target_file = Column(String, index=True)  # 指向的原始图片文件名
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    access_count = Column(BigInteger, default=0)  # 访问计数
    expire_at = Column(DateTime, nullable=True)  # 过期时间，为null则永不过期
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # 关系
    user = relationship("User")
    
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

# 创建管理员账户
def create_admin_user(db):
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "123456")
    
    # 检查管理员是否已存在
    admin = db.query(User).filter(User.username == admin_username).first()
    if not admin:
        admin = User(
            username=admin_username,
            email=admin_email,
            password=admin_password,
            is_admin=True
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"管理员账户已创建: {admin_username}")
    return admin 