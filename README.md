# PicUI - 简单高效的图床服务

一个基于FastAPI开发的轻量级图床服务，支持多种图片格式上传、存储和管理。

![版本](https://img.shields.io/badge/版本-1.0.0-blue)
![许可证](https://img.shields.io/badge/许可证-MIT-green)

## 特性

- 💻 简洁美观的上传界面，支持拖拽上传
- ⚡ 高效的图片处理和存储机制
- 🗄️ SQLite数据库存储图片元数据
- 🔄 一键复制图片链接、HTML和Markdown代码
- 📱 响应式设计，适配各种设备
- 🚀 支持Docker容器化部署
- ☁️ 支持Railway、Render等云平台部署

## 快速开始

### 前提条件

- Python 3.8+
- pip

### 本地安装

1. 克隆仓库
```bash
git clone https://github.com/yourusername/picui.git
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
   - 点击"上传图片"按钮
   - 上传完成后可获取图片链接

2. 通过API上传:
   - 发送POST请求到 `/upload` 端点
   - 请求体使用 `multipart/form-data` 格式，包含 `file` 字段

### API文档

访问 [http://localhost:8000/docs](http://localhost:8000/docs) 查看完整的API文档。

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

## 贡献指南

欢迎贡献代码或提出建议，请查看 [贡献指南.md](贡献指南.md) 了解详情。

## 许可证

本项目采用 MIT 许可证，详情见 [LICENSE](LICENSE) 文件。

## 联系方式

如有问题或建议，请通过 GitHub Issues 与我们联系。 