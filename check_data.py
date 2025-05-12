from src.database import get_db, UploadLog, ShortLink, Image
import sys

def check_database():
    """检查数据库中的数据"""
    print("======= 数据库检查开始 =======")
    db = next(get_db())
    
    # 检查上传日志
    logs_count = db.query(UploadLog).count()
    print(f"上传日志数量: {logs_count}")
    
    # 检查短链接
    links_count = db.query(ShortLink).count()
    print(f"短链接数量: {links_count}")
    
    # 检查图片
    images_count = db.query(Image).count()
    print(f"图片数量: {images_count}")
    
    # 如果有数据，显示几条
    if logs_count > 0:
        print("\n=== 上传日志样例 ===")
        logs = db.query(UploadLog).order_by(UploadLog.id.desc()).limit(3).all()
        for i, log in enumerate(logs):
            print(f"日志 #{i+1}: ID={log.id}, 用户ID={log.user_id}, 文件名={log.original_filename}, 状态={log.status}")
    
    if links_count > 0:
        print("\n=== 短链接样例 ===")
        links = db.query(ShortLink).order_by(ShortLink.created_at.desc()).limit(3).all()
        for i, link in enumerate(links):
            print(f"短链接 #{i+1}: code={link.code}, 用户ID={link.user_id}, 目标文件={link.target_file}")
    
    if images_count > 0:
        print("\n=== 图片样例 ===")
        images = db.query(Image).order_by(Image.id.desc()).limit(3).all()
        for i, img in enumerate(images):
            print(f"图片 #{i+1}: ID={img.id}, 用户ID={img.user_id}, 文件名={img.filename}")
    
    print("\n======= 数据库检查结束 =======")

if __name__ == "__main__":
    check_database()
    sys.exit(0) 