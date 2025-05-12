#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PicUI图床服务 - 入口文件
提供快速高效的图片上传托管服务
"""
import os
import uvicorn
import asyncio
import multiprocessing
import time
import shutil
from datetime import datetime
import logging

# 控制台颜色定义
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# 尝试导入dotenv，如果不可用则跳过
try:
    from dotenv import load_dotenv
    # 加载环境变量
    load_dotenv()
    print(f"{Colors.GREEN}✓ 已加载.env环境变量{Colors.ENDC}")
except ImportError:
    print(f"{Colors.YELLOW}! python-dotenv未安装，将使用默认配置{Colors.ENDC}")

# 获取环境变量中的配置
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")
WORKERS = int(os.getenv("WORKERS", 8))
LOGLEVEL = os.getenv("LOGLEVEL", "info").lower()  # 默认使用info级别，可以看到更多日志
RELOAD = os.getenv("RELOAD", "false").lower() == "true"

# 设置日志级别映射
log_levels = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL
}

# 获取实际日志级别
log_level = log_levels.get(LOGLEVEL, logging.ERROR)

# 配置日志
logging.basicConfig(
    level=log_level,
    format="%(levelname)s:%(name)s:%(message)s"
)

# 清理过大的日志文件
def cleanup_logs():
    """清理过期日志文件"""
    log_file = "upload.log"
    if os.path.exists(log_file) and os.path.getsize(log_file) > 10 * 1024 * 1024:  # 超过10MB
        print(f"{Colors.YELLOW}日志文件过大，进行清理...{Colors.ENDC}")
        # 备份旧日志
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_file = f"upload_{timestamp}.log.bak"
        shutil.copy2(log_file, backup_file)
        # 清空当前日志
        open(log_file, 'w').close()
        print(f"{Colors.GREEN}✓ 日志已清理并备份到 {backup_file}{Colors.ENDC}")

def print_banner():
    """打印美化的启动横幅"""
    banner = f"""
{Colors.CYAN}+----------------------------------------+{Colors.ENDC}
{Colors.CYAN}|                                        |{Colors.ENDC}
{Colors.CYAN}|   {Colors.BOLD}{Colors.HEADER}██████╗ ██╗ ██████╗██╗   ██╗██╗{Colors.CYAN}    |{Colors.ENDC}
{Colors.CYAN}|   {Colors.BOLD}{Colors.HEADER}██╔══██╗██║██╔════╝██║   ██║██║{Colors.CYAN}    |{Colors.ENDC}
{Colors.CYAN}|   {Colors.BOLD}{Colors.HEADER}██████╔╝██║██║     ██║   ██║██║{Colors.CYAN}    |{Colors.ENDC}
{Colors.CYAN}|   {Colors.BOLD}{Colors.HEADER}██╔═══╝ ██║██║     ██║   ██║██║{Colors.CYAN}    |{Colors.ENDC}
{Colors.CYAN}|   {Colors.BOLD}{Colors.HEADER}██║     ██║╚██████╗╚██████╔╝██║{Colors.CYAN}    |{Colors.ENDC}
{Colors.CYAN}|   {Colors.BOLD}{Colors.HEADER}╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚═╝{Colors.CYAN}    |{Colors.ENDC}
{Colors.CYAN}|                                        |{Colors.ENDC}
{Colors.CYAN}|   {Colors.GREEN}高效简洁的图床服务 v1.0.0{Colors.CYAN}             |{Colors.ENDC}
{Colors.CYAN}|   {Colors.YELLOW}启动时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}{Colors.CYAN}   |{Colors.ENDC}
{Colors.CYAN}+----------------------------------------+{Colors.ENDC}
"""
    print(banner)

def print_config():
    """打印配置信息"""
    reload_str = "是" if RELOAD else "否"
    config = f"""
{Colors.CYAN}+----------------------------------------+{Colors.ENDC}
{Colors.CYAN}|  {Colors.BOLD}配置信息{Colors.ENDC}{Colors.CYAN}                               |{Colors.ENDC}
{Colors.CYAN}|----------------------------------------|{Colors.ENDC}
{Colors.CYAN}|  {Colors.YELLOW}监听地址:{Colors.CYAN} {Colors.GREEN}{HOST}:{PORT}{Colors.CYAN}                 |{Colors.ENDC}
{Colors.CYAN}|  {Colors.YELLOW}工作进程:{Colors.CYAN} {Colors.GREEN}{WORKERS}{Colors.CYAN}                       |{Colors.ENDC}
{Colors.CYAN}|  {Colors.YELLOW}日志级别:{Colors.CYAN} {Colors.GREEN}{LOGLEVEL}{Colors.CYAN}                     |{Colors.ENDC}
{Colors.CYAN}|  {Colors.YELLOW}热重载:  {Colors.CYAN} {Colors.GREEN}{reload_str}{Colors.CYAN}                       |{Colors.ENDC}
{Colors.CYAN}+----------------------------------------+{Colors.ENDC}
"""
    print(config)

def main():
    """
    主入口函数
    使用uvicorn启动FastAPI应用，根据CPU核心数自动配置工作进程
    """
    # 清理过大的日志文件
    cleanup_logs()
    
    # 从src.database导入并执行数据库升级
    try:
        from src.database import upgrade_database
        print(f"{Colors.BLUE}正在升级数据库结构...{Colors.ENDC}")
        upgrade_database()
        print(f"{Colors.GREEN}✓ 数据库升级完成{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.RED}! 数据库升级失败: {str(e)}{Colors.ENDC}")
    
    print_banner()
    print_config()
    
    # 启动动画
    print(f"{Colors.GREEN}正在启动服务器...{Colors.ENDC}")
    for _ in range(5):
        time.sleep(0.2)
        print(f"{Colors.CYAN}.", end="", flush=True)
    print(f"{Colors.ENDC}\n")
    
    # 启动服务器
    uvicorn.run(
        "src.app:app", 
        host=HOST, 
        port=PORT, 
        reload=RELOAD,
        workers=WORKERS if not RELOAD else 1,  # reload模式下只能使用1个worker
        log_level=LOGLEVEL
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}接收到中断信号，正在停止服务...{Colors.ENDC}")
        print(f"{Colors.GREEN}✓ PicUI服务已安全停止{Colors.ENDC}")
