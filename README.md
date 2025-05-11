# PicUI 图床服务

PicUI是一个基于FastAPI的简单高效图床服务，支持图片上传、存储、访问和分享。通过简洁的界面和强大的API，让图片管理变得轻松便捷。

🔗 **在线体验**: [测试地址](http://117.72.85.101:8000/)（服务器配置较低，访问可能较慢，请见谅）  
📦 **仓库地址**: [GitHub - laozig/picui](https://github.com/laozig/picui.git)

## 主要功能

- **便捷上传**：支持拖拽上传、粘贴上传和API上传
- **多格式支持**：兼容JPG、PNG、GIF、WEBP、BMP、TIFF、SVG、ICO、HEIC等多种图片格式
- **图像处理**：自动优化图片尺寸、添加自定义水印
- **安全可控**：用户系统、权限控制、内容安全检测
- **分享功能**：短链接生成、临时外链、HTML/Markdown代码生成
- **监控统计**：Prometheus指标支持、上传日志记录
- **防盗措施**：IP白名单限制、防盗链配置、频率限制
- **部署灵活**：支持Docker、Railway、Render等多种部署方式

## 预览

### 上传界面
![上传界面](1.png)

### API界面
![API界面](2.png)

## 快速开始

### 安装依赖

```bash
# 创建虚拟环境（可选但推荐）
python -m venv venv_picui
source venv_picui/bin/activate  # Linux/Mac
# 或
venv_picui\Scripts\activate     # Windows

# 使用国内镜像源安装依赖（可选）
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
# 或直接安装
pip install -r requirements.txt
```

### 运行服务

```bash
# 方法1：直接运行（开发模式）
python main.py

# 方法2：使用uvicorn（生产环境）
uvicorn main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 打开图床主页。

### API上传示例

```bash
# 使用curl上传图片
curl -X POST "http://localhost:8000/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_image.jpg;type=image/jpeg" \
  -F "token=mysecrettoken"

# Python示例
import requests
response = requests.post(
    "http://localhost:8000/upload",
    files={"file": open("your_image.jpg", "rb")},
    data={"token": "mysecrettoken"}
)
print(response.json())
```

## 支持的图片格式

PicUI支持以下图片格式：
- jpg, jpeg, png, gif, webp
- bmp, tiff, tif, svg, ico
- heic, heif, avif, jfif, pjpeg, pjp

## 详细配置

### 环境变量

所有配置项都可以通过环境变量设置，无需修改代码：

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `PORT` | 服务端口号 | 8000 |
| `HOST` | 服务监听地址 | 0.0.0.0 |
| `BASE_URL` | 服务基础URL | http://localhost:8000 |
| `UPLOAD_DIR` | 图片上传目录 | uploads |
| `MAX_FILE_SIZE` | 最大文件大小(字节) | 20971520 (20MB) |
| `DATABASE_URL` | 数据库连接URL | sqlite:///./picui.db |
| `ADMIN_USERNAME` | 管理员用户名 | admin |
| `ADMIN_PASSWORD` | 管理员密码 | 123456 |
| `API_TOKEN` | API令牌 | mysecrettoken |
| `RATE_LIMIT` | 频率限制(每分钟) | 20 |
| `MAX_CONCURRENT_UPLOADS` | 最大并发上传数 | 20 |
| `DISK_CHECK_INTERVAL` | 磁盘检查间隔(秒) | 3600 |
| `DISK_USAGE_THRESHOLD` | 磁盘使用阈值(%) | 80.0 |

### 数据库配置

默认使用SQLite数据库，如需使用其他数据库，设置`DATABASE_URL`环境变量：

```
# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/picui

# MySQL/MariaDB
DATABASE_URL=mysql://user:password@localhost:3306/picui
```

## 目录结构

```
picui/
├── main.py                # FastAPI应用主文件
├── database.py            # 数据库模型和配置
├── static/                # 静态文件
│   └── index.html         # 前端上传页面
├── uploads/               # 上传文件存储目录
├── requirements.txt       # 项目依赖
├── Dockerfile             # Docker配置
├── README.md              # 项目文档
├── 服务器部署指南.md      # 服务器部署文档
├── 云平台部署指南.md      # 云平台部署文档
├── GitHub设置指南.md      # GitHub设置文档
└── 贡献指南.md            # 贡献指南
```

## 高级功能

### 图片优化

PicUI会自动优化上传的图片：
- 限制最长边不超过1920像素(可配置)
- 保持原始比例
- 优化图片质量和文件大小

### 水印功能

支持为图片添加自定义水印文字：

```
GET /images/{filename}/watermark?text=自定义水印&position=bottom-right&opacity=0.7
```

参数说明：
- `text`: 水印文字内容
- `position`: 位置(center, bottom-right, bottom-left, top-right, top-left)
- `opacity`: 不透明度(0.1-1.0)

### 短链接生成

每张上传的图片自动生成短链接，访问格式：

```
http://your-domain.com/s/{短码}
```

### 临时外链

创建带有有效期的临时访问链接：

```
POST /create-temp-link/{image_id}?expire_minutes=60
```

## 内容安全检测

PicUI提供两种图片内容安全检测方式：

### 1. 阿里云内容安全检测

使用阿里云内容安全服务进行专业的图片内容检测，可以识别涉黄、涉政、暴力等不良内容。

配置参数:
```
ALIYUN_ACCESS_KEY_ID=你的阿里云AccessKeyId
ALIYUN_ACCESS_KEY_SECRET=你的阿里云AccessKeySecret
ALIYUN_REGION=cn-shanghai
CONTENT_CHECK_ENABLED=true
```

### 2. 离线内容检测

提供一个简单的本地离线检测功能，通过分析图片中的肤色比例进行基础检测。

配置参数:
```
OFFLINE_CHECK_ENABLED=true
SKIN_THRESHOLD=0.5  # 肤色像素占比阈值，0.0-1.0之间
```

注意：离线检测精度有限，仅作为云端检测的备选方案，建议在生产环境中使用阿里云内容安全服务。

## 安全配置

### IP白名单

限制管理后台访问的IP地址：
```
IP_WHITELIST=127.0.0.1/32,192.168.0.0/16,10.0.0.0/8
```

### 防盗链

限制图片访问的来源网站：
```
ALLOWED_REFERERS=localhost,example.com,yourdomain.com
```

### 两步验证

支持基于TOTP的两步验证，增强账户安全性：
1. 管理员登录后可以在个人设置中启用
2. 使用Google Authenticator等TOTP应用扫描二维码
3. 登录时需要输入动态验证码

## API文档

启动服务后，可以访问以下地址查看完整API文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

### 主要API端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /upload | 上传图片 |
| GET | /images/{filename} | 查看图片 |
| GET | /images/{filename}/watermark | 获取带水印的图片 |
| GET | /s/{code} | 访问短链接 |
| POST | /create-temp-link/{image_id} | 创建临时外链 |
| GET | /metrics | 查看监控指标(需管理员权限) |
| GET | /logs | 查看上传日志(需管理员权限) |

## 使用说明

### 上传图片

1. 通过网页界面上传:  
   * 点击"选择图片"或者将图片拖拽到上传区域  
   * 输入访问令牌（默认为"mysecrettoken"）  
   * 点击"上传图片"按钮  
   * 上传完成后可获取图片链接、HTML和Markdown代码  
   * 可以点击"在新窗口打开"查看原图  
   * 可以点击"上传另一张"继续上传

2. 通过API上传:  
   * 发送POST请求到 `/upload` 端点  
   * 请求体使用 `multipart/form-data` 格式，包含 `file` 和 `token` 字段  
   * 返回JSON包含图片URL和ID

## 监控与统计

### Prometheus指标

PicUI集成了Prometheus监控，提供以下指标：

- `pic_uploads_total`: 总上传次数
- `pic_upload_failures_total`: 上传失败次数
- `pic_deletions_total`: 删除次数
- `pic_disk_usage_percent`: 上传目录磁盘使用率
- `pic_upload_size_bytes`: 上传文件大小(字节)

访问`/metrics`端点(需管理员权限)获取这些指标。

### 上传日志

系统自动记录所有上传活动，包括：
- 上传时间
- 文件大小
- 原始文件名
- 客户端IP
- User-Agent
- 成功/失败状态

管理员可以通过`/logs`页面查看这些日志。

## 部署

### Docker部署

```bash
# 构建镜像
docker build -t picui .

# 运行容器
docker run -d -p 8000:8000 \
  -v $(pwd)/uploads:/app/uploads \
  -e ADMIN_PASSWORD=your_secure_password \
  --name picui picui
```

### 系统服务部署

#### Linux (systemd)

创建服务文件`/etc/systemd/system/picui.service`：

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

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl enable picui
sudo systemctl start picui
```

#### Windows (NSSM)

使用NSSM创建Windows服务：
```
nssm install PicUI "C:\picui\venv\Scripts\python.exe" "C:\picui\main.py"
nssm set PicUI AppDirectory "C:\picui"
nssm start PicUI
```

### 云平台部署

支持多种云平台，详细说明见以下文档：
- [服务器部署指南](服务器部署指南.md)
- [云平台部署指南](云平台部署指南.md)
- [GitHub设置指南](GitHub设置指南.md)

## 技术栈

* FastAPI - Web框架
* SQLAlchemy - ORM框架
* Uvicorn - ASGI服务器
* TailwindCSS - CSS框架
* Prometheus - 监控指标
* Python-Multipart - 处理文件上传
* Pillow - 图像处理

## 性能优化建议

- 使用生产级WSGI服务器如Gunicorn
- 配置Nginx反向代理处理静态文件
- 对于高流量应用，考虑使用CDN分发图片
- 定期清理未使用的上传图片
- 启用数据库缓存和连接池

## 贡献

欢迎贡献代码和提出建议！请查看[贡献指南](贡献指南.md)了解如何参与项目开发。

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/laozig/picui.git
cd picui

# 安装开发依赖
pip install -r requirements.txt
pip install pytest pytest-cov black flake8

# 运行测试
pytest

# 代码格式化
black .
flake8
```

## 常见问题

1. **上传失败**
   - 检查图片格式是否支持
   - 确认图片大小未超过限制（默认20MB）
   - 验证上传目录是否存在且有写入权限
   - 查看服务器日志获取详细错误信息

2. **图片无法访问**
   - 检查防盗链设置是否限制了访问
   - 确认文件是否已成功上传到正确位置
   - 验证文件权限是否正确

3. **服务无法启动**
   - 检查端口是否被占用
   - 确认所有依赖已正确安装
   - 检查数据库连接是否正常
   - 查看日志文件获取详细错误信息

4. **性能问题**
   - 检查并发上传数设置是否合理
   - 考虑使用外部对象存储服务
   - 启用图片缓存和CDN

5. **安全问题**
   - 确保管理员密码足够强
   - 启用两步验证
   - 定期更新依赖包
   - 限制上传IP和访问频率

## 更新日志

### v1.0.0
- 初始版本发布
- 基本图片上传和管理功能
- 用户系统和权限控制
- 水印和图片优化功能

## 联系方式

如有问题或建议，请通过 [GitHub Issues](https://github.com/laozig/picui/issues) 与我们联系。

## 许可证

本项目基于MIT许可证开源 - 详情见[LICENSE](LICENSE)文件