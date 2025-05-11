# PicUI - 简洁高效的图床服务

一个基于FastAPI开发的现代化图床服务，支持多种图片格式上传、存储和管理。

![版本](https://img.shields.io/badge/版本-1.0.0-blue)
![许可证](https://img.shields.io/badge/许可证-MIT-green)
![Python](https://img.shields.io/badge/Python-3.8+-yellow)
![FastAPI](https://img.shields.io/badge/FastAPI-0.103.1-teal)

## 在线体验

🔗 [测试地址](http://117.72.85.101:8000/) (服务器配置较低，访问可能较慢，请见谅)

## 特性

- 🎨 精美现代的用户界面，支持拖拽上传
- 🖼️ 支持16种常见图片格式，包括JPG、PNG、GIF、WEBP等
- 📦 最大支持15MB图片上传
- 🔗 一键复制图片链接、HTML和Markdown代码
- 🗄️ SQLite数据库存储图片元数据
- 📱 响应式设计，完美适配各种设备
- 🚀 支持Docker容器化部署
- ☁️ 支持Railway、Render等云平台部署
- 📝 完整的中文API文档
- 🛡️ 内置频率限制，防止滥用
- 🔐 Token验证机制，确保安全上传
- 🚦 并发控制，防止DDoS攻击

## 预览

### 上传界面
![上传界面](./1.png)

### API界面
![API界面](./2.png)

## 快速开始

### 前提条件

- Python 3.8+
- pip

### 本地安装

1. 克隆仓库
```bash
git clone https://github.com/laozig/picui.git
cd picui
```

2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 启动应用
```bash
python main.py
```

5. 访问应用
打开浏览器访问 [http://localhost:8000](http://localhost:8000)

## 使用说明

### 上传图片

1. 通过网页界面上传:
   - 点击"选择图片"或者将图片拖拽到上传区域
   - 输入访问令牌（默认为"mysecrettoken"）
   - 点击"上传图片"按钮
   - 上传完成后可获取图片链接、HTML和Markdown代码
   - 可以点击"在新窗口打开"查看原图
   - 可以点击"上传另一张"继续上传

2. 通过API上传:
   - 发送POST请求到 `/upload` 端点
   - 请求体使用 `multipart/form-data` 格式，包含 `file` 和 `token` 字段
   - 返回JSON包含图片URL和ID

### 支持的图片格式

PicUI支持以下图片格式：
- jpg, jpeg, png, gif, webp
- bmp, tiff, tif, svg, ico
- heic, heif, avif, jfif, pjpeg, pjp

### API文档

访问 [http://localhost:8000/docs](http://localhost:8000/docs) 查看完整的中文API文档。

## 部署指南

### Docker部署

```bash
# 构建镜像
docker build -t picui .

# 运行容器
docker run -d -p 8000:8000 -v $(pwd)/uploads:/app/uploads --name picui picui
```

### 云平台部署

详细的云平台部署指南请查看 [云平台部署指南.md](云平台部署指南.md)。

### 服务器部署

完整的服务器部署说明（Ubuntu和Windows）请查看 [服务器部署指南.md](服务器部署指南.md)。

## 技术栈

- [FastAPI](https://fastapi.tiangolo.com/) - Web框架
- [SQLAlchemy](https://www.sqlalchemy.org/) - ORM框架
- [Uvicorn](https://www.uvicorn.org/) - ASGI服务器
- [TailwindCSS](https://tailwindcss.com/) - CSS框架

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

## 环境变量配置

PicUI支持以下环境变量配置：

- `PORT`: 应用监听端口（默认: 8000）
- `HOST`: 应用监听地址（默认: 0.0.0.0）
- `BASE_URL`: 应用基础URL（默认: http://localhost:PORT）
- `UPLOAD_DIR`: 上传文件存储目录（默认: uploads）
- `MAX_FILE_SIZE`: 最大文件大小（字节，默认: 15MB）
- `DATABASE_URL`: 数据库URL（默认: sqlite:///./picui.db）
- `RATE_LIMIT`: 每分钟最大上传请求数（默认: 20）
- `RATE_LIMIT_WINDOW`: 频率限制时间窗口，单位秒（默认: 60）
- `API_TOKEN`: 上传接口访问令牌（默认: mysecrettoken）
- `MAX_CONCURRENT_UPLOADS`: 最大并发上传数（默认: 20）

## 贡献指南

欢迎贡献代码或提出建议，请查看 [贡献指南.md](贡献指南.md) 了解详情。

## 许可证

本项目采用 MIT 许可证，详情见 [LICENSE](LICENSE) 文件。

## 联系方式

如有问题或建议，请通过 GitHub Issues 与我们联系。 