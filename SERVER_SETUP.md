# 服务器部署配置指南

本文档提供在Ubuntu和Windows服务器上部署PicUI图床服务的详细步骤。

## 目录

- [Ubuntu服务器部署](#ubuntu服务器部署)
- [Windows服务器部署](#windows服务器部署)
- [Nginx反向代理配置](#nginx反向代理配置)
- [SSL证书配置](#ssl证书配置)
- [数据备份](#数据备份)

## Ubuntu服务器部署

### 安装依赖

```bash
# 更新系统包
sudo apt update
sudo apt upgrade -y

# 安装Python和相关工具
sudo apt install -y python3 python3-pip python3-venv git
```

### 拉取代码并安装

```bash
# 创建应用目录
mkdir -p /opt/picui
cd /opt/picui

# 克隆代码（如果使用Git）
git clone https://github.com/你的用户名/picui.git .
# 或者手动上传代码到服务器

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 配置服务

1. 创建systemd服务配置文件：

```bash
sudo nano /etc/systemd/system/picui.service
```

2. 添加以下内容：

```ini
[Unit]
Description=PicUI Image Hosting Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/picui
ExecStart=/opt/picui/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
Environment="PYTHONPATH=/opt/picui"
Environment="UPLOAD_DIR=/opt/picui/uploads"
Environment="MAX_FILE_SIZE=5242880"
# 如果需要使用外部数据库，取消注释下一行并修改
# Environment="DATABASE_URL=postgresql://user:password@localhost:5432/picuidb"

[Install]
WantedBy=multi-user.target
```

3. 修改目录权限：

```bash
sudo mkdir -p /opt/picui/uploads
sudo chown -R www-data:www-data /opt/picui
```

4. 启用并启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable picui
sudo systemctl start picui
```

5. 查看服务状态：

```bash
sudo systemctl status picui
```

### 使用Screen运行（替代方法）

如果不想设置systemd服务，可以使用Screen在后台运行：

```bash
# 安装screen
sudo apt install -y screen

# 创建新screen会话
screen -S picui

# 激活虚拟环境
source venv/bin/activate

# 启动应用
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 按 Ctrl+A 然后按 D 可以分离screen会话
# 使用以下命令可以重新连接到会话
# screen -r picui
```

## Windows服务器部署

### 安装Python

1. 下载并安装Python 3.8+，从[Python官网](https://www.python.org/downloads/windows/)
2. 安装时勾选"Add Python to PATH"选项

### 拉取代码并安装

```powershell
# 创建应用目录
mkdir C:\picui
cd C:\picui

# 如果使用Git，安装Git并克隆代码
# git clone https://github.com/你的用户名/picui.git .
# 或者手动复制代码到服务器

# 创建虚拟环境
python -m venv venv
.\venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 使用NSSM设置Windows服务

1. 下载[NSSM](http://nssm.cc/download)并解压
2. 将nssm.exe复制到系统PATH中的目录（如C:\Windows\System32）
3. 创建一个启动脚本(start_picui.bat)：

```batch
@echo off
cd C:\picui
call venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

4. 使用NSSM创建服务：

```powershell
# 打开管理员命令提示符并运行
nssm install PicUI

# 在弹出窗口中配置以下内容：
# Path: C:\picui\start_picui.bat
# Startup directory: C:\picui
# 在Details标签下设置服务名称和描述
# 在Environment标签下添加必要的环境变量:
# UPLOAD_DIR=C:\picui\uploads
# MAX_FILE_SIZE=5242880
```

5. 启动服务：

```powershell
nssm start PicUI
```

### 使用PowerShell在后台运行（替代方法）

如果不想设置Windows服务，可以使用PowerShell在后台运行：

```powershell
Start-Process -NoNewWindow -FilePath "C:\picui\venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000" -WorkingDirectory "C:\picui"
```

## Nginx反向代理配置

在生产环境中，建议使用Nginx作为前端反向代理服务器。

### Ubuntu上安装Nginx

```bash
sudo apt install -y nginx
```

### 配置Nginx反向代理

创建Nginx配置文件：

```bash
sudo nano /etc/nginx/sites-available/picui
```

添加以下内容：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名或服务器IP

    client_max_body_size 10M;  # 允许最大上传文件大小

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 如果想直接提供静态文件（可选）
    location /static/ {
        alias /opt/picui/static/;
    }

    location /uploads/ {
        alias /opt/picui/uploads/;
    }
}
```

启用站点并重启Nginx：

```bash
sudo ln -s /etc/nginx/sites-available/picui /etc/nginx/sites-enabled/
sudo nginx -t  # 测试配置
sudo systemctl restart nginx
```

### Windows上的Nginx配置

1. 从[官网](http://nginx.org/en/download.html)下载Windows版Nginx
2. 解压到C:\nginx
3. 创建配置文件C:\nginx\conf\sites-enabled\picui.conf：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名或服务器IP

    client_max_body_size 10M;  # 允许最大上传文件大小

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 如果想直接提供静态文件（可选）
    location /static/ {
        alias C:/picui/static/;
    }

    location /uploads/ {
        alias C:/picui/uploads/;
    }
}
```

4. 在nginx.conf的http块中添加：`include conf/sites-enabled/*.conf;`
5. 启动Nginx：

```powershell
# 以管理员权限运行PowerShell
cd C:\nginx
.\nginx.exe
```

## SSL证书配置

### 使用Let's Encrypt (Ubuntu)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### 手动SSL配置 (Windows或Ubuntu)

1. 获取SSL证书文件（.crt和.key）
2. 修改Nginx配置：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;
    
    # SSL优化配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_session_timeout 10m;
    ssl_session_cache shared:SSL:10m;
    
    # 其他配置同上...
}

# 重定向HTTP到HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}
```

## 数据备份

### 备份脚本 (Ubuntu)

创建备份脚本：

```bash
sudo nano /opt/picui/backup.sh
```

添加以下内容：

```bash
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR="/opt/backups/picui"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
cp /opt/picui/picui.db $BACKUP_DIR/picui_$DATE.db

# 备份上传的文件
tar -czf $BACKUP_DIR/uploads_$DATE.tar.gz /opt/picui/uploads

# 删除7天前的备份
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
```

添加执行权限并设置定时任务：

```bash
sudo chmod +x /opt/picui/backup.sh
sudo crontab -e
```

添加以下行设置每天凌晨3点执行备份：

```
0 3 * * * /opt/picui/backup.sh
```

### 备份脚本 (Windows)

创建备份脚本(backup.bat)：

```batch
@echo off
set DATE=%date:~0,4%%date:~5,2%%date:~8,2%
set BACKUP_DIR=C:\backups\picui

:: 创建备份目录
if not exist %BACKUP_DIR% mkdir %BACKUP_DIR%

:: 备份数据库
copy C:\picui\picui.db %BACKUP_DIR%\picui_%DATE%.db

:: 备份上传的文件
powershell -Command "Compress-Archive -Path 'C:\picui\uploads' -DestinationPath '%BACKUP_DIR%\uploads_%DATE%.zip'"

:: 删除7天前的备份
forfiles /p %BACKUP_DIR% /m *.db /d -7 /c "cmd /c del @path"
forfiles /p %BACKUP_DIR% /m *.zip /d -7 /c "cmd /c del @path"
```

使用Windows计划任务：
1. 打开任务计划程序
2. 创建基本任务
3. 设置每天执行，选择时间
4. 选择"启动程序"
5. 选择backup.bat文件
6. 完成设置 