from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

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
    size = Column(Float)  # 以KB为单位
    mime_type = Column(String)
    upload_time = Column(DateTime, default=datetime.datetime.utcnow)
    
    def __repr__(self):
        return f"<Image {self.filename}>"

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