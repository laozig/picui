# 图床服务部署指南

本文档提供在不同云平台上部署此图床服务的详细说明，包括文件持久化配置。

## 环境变量配置

应用支持以下环境变量：

- `PORT`: 应用监听端口（默认: 8000）
- `HOST`: 应用监听地址（默认: 0.0.0.0）
- `BASE_URL`: 应用基础URL（默认: http://localhost:PORT）
- `UPLOAD_DIR`: 上传文件存储目录（默认: uploads）
- `MAX_FILE_SIZE`: 最大文件大小（字节，默认: 5242880，即5MB）
- `DATABASE_URL`: 数据库URL（默认: sqlite:///./picui.db）

## Docker 部署

使用以下命令构建并运行Docker容器：

```bash
# 构建镜像
docker build -t picui .

# 运行容器
docker run -d -p 8000:8000 -v $(pwd)/uploads:/app/uploads --name picui picui
```

## Railway 部署

1. 安装 Railway CLI (可选)：
```bash
npm install -g @railway/cli
```

2. 登录 Railway：
```bash
railway login
```

3. 初始化项目：
```bash
railway init
```

4. 部署到 Railway：
```bash
railway up
```

5. 配置持久存储：

在 Railway 控制台 -> 项目设置 -> 挂载点，添加新的持久卷：
- 卷名称：uploads
- 路径：/app/uploads

## Render 部署

1. 登录 [Render Dashboard](https://dashboard.render.com/)
2. 点击 "New Web Service"
3. 选择从 GitHub 导入项目
4. 配置以下设置：
   - 运行时环境：Docker
   - 分支：main
   - 构建命令：不需要（使用Dockerfile）
   - 启动命令：不需要（使用Dockerfile）
   
5. 配置持久存储：
   - 在部署后，进入服务设置
   - 添加磁盘：
     - 名称：uploads
     - 挂载路径：/app/uploads
     - 大小：至少1GB

## 数据库配置

默认使用SQLite数据库，存储在应用目录中。对于生产环境，建议使用外部数据库：

1. 在云平台上创建PostgreSQL或MySQL数据库
2. 设置环境变量 `DATABASE_URL` 为数据库连接字符串，如：
   - PostgreSQL: `postgresql://user:password@hostname:port/dbname`
   - MySQL: `mysql://user:password@hostname:port/dbname`

## 确保文件持久化

为了确保上传的文件不会在应用重启后丢失，请务必按照上面指南配置持久存储。

## 安全注意事项

1. 在生产环境中，建议使用HTTPS
2. 考虑添加身份验证和授权机制
3. 定期备份数据库和上传的文件

## 故障排查

1. 应用无法启动：检查环境变量配置和日志
2. 上传失败：检查持久卷挂载是否正确
3. 文件不可访问：检查文件权限和路径配置 