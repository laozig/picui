# PicUI GitHub设置指南

本文档将指导您如何将PicUI项目上传到GitHub并进行完整的初始设置，包括CI/CD配置和自动化部署。

## 步骤1：创建GitHub账号

如果您还没有GitHub账号，请先在 [GitHub官网](https://github.com/) 注册一个账号。

## 步骤2：创建新仓库

1. 登录到GitHub
2. 点击右上角的"+"图标，然后选择"New repository"
3. 填写仓库名称(例如：picui)
4. 添加项目描述："一个简洁高效的图床服务，基于FastAPI开发"
5. 选择仓库可见性：
   - "Public"：对所有人可见（推荐用于开源项目）
   - "Private"：仅对您和您邀请的协作者可见
6. 选择"Add a README file"（初始化仓库）
7. 选择"Add .gitignore"并选择"Python"模板
8. 选择"Choose a license"并选择"MIT License"（或您偏好的许可证）
9. 点击"Create repository"

## 步骤3：克隆仓库并添加项目文件

```bash
# 克隆新创建的仓库
git clone https://github.com/laozig/picui.git
cd picui

# 复制项目文件到仓库目录
# (假设您的项目文件在另一个目录中)
cp -r /path/to/your/project/* .

# 添加所有文件到暂存区
git add .

# 提交更改
git commit -m "初始化PicUI项目"

# 推送到GitHub
git push origin main
```

## 步骤4：配置GitHub Actions

GitHub Actions可以帮助您自动化测试、构建和部署流程。

### 创建Python测试工作流

1. 在仓库根目录创建`.github/workflows`文件夹：
```bash
mkdir -p .github/workflows
```

2. 创建`python-app.yml`文件：
```bash
nano .github/workflows/python-app.yml
```

3. 添加以下内容：
```yaml
name: Python应用测试

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, '3.10']

    steps:
    - uses: actions/checkout@v3
    - name: 设置Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    - name: 安装依赖
      run: |
        python -m pip install --upgrade pip
        if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
        pip install pytest pytest-cov
    - name: 运行测试
      run: |
        pytest --cov=./ --cov-report=xml
    - name: 上传覆盖率报告
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        fail_ci_if_error: true
```

4. 提交并推送工作流配置：
```bash
git add .github/workflows/python-app.yml
git commit -m "添加GitHub Actions测试工作流"
git push origin main
```

### 创建Docker构建工作流（可选）

如果您想自动构建Docker镜像，可以创建另一个工作流：

1. 创建`docker-build.yml`文件：
```bash
nano .github/workflows/docker-build.yml
```

2. 添加以下内容：
```yaml
name: Docker构建

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: 登录到DockerHub
      uses: docker/login-action@v2
      with:
        username: ${{ secrets.DOCKERHUB_USERNAME }}
        password: ${{ secrets.DOCKERHUB_TOKEN }}
        
    - name: 提取元数据
      id: meta
      uses: docker/metadata-action@v4
      with:
        images: 你的用户名/picui
        tags: |
          type=semver,pattern={{version}}
          type=ref,event=branch
          
    - name: 构建并推送
      uses: docker/build-push-action@v4
      with:
        context: .
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
```

3. 在GitHub仓库设置中添加Secrets：
   - 进入仓库 -> Settings -> Secrets and variables -> Actions
   - 添加`DOCKERHUB_USERNAME`和`DOCKERHUB_TOKEN`

## 步骤5：配置项目徽章

在`README.md`中添加项目状态徽章：

```markdown
[![Python应用测试](https://github.com/你的用户名/picui/actions/workflows/python-app.yml/badge.svg)](https://github.com/你的用户名/picui/actions/workflows/python-app.yml)
[![codecov](https://codecov.io/gh/你的用户名/picui/branch/main/graph/badge.svg)](https://codecov.io/gh/你的用户名/picui)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
```

## 步骤6：配置GitHub Pages

如果您想为项目创建文档网站：

1. 创建`docs`文件夹并添加文档：
```bash
mkdir -p docs
# 复制或创建文档文件到docs文件夹
```

2. 在GitHub仓库页面：
   - 点击"Settings" -> "Pages"
   - 在"Source"下选择"Deploy from a branch"
   - 选择"main"分支和"/docs"文件夹
   - 点击"Save"

3. 创建简单的index.html文件：
```bash
nano docs/index.html
```

添加基本内容：
```html
<!DOCTYPE html>
<html>
<head>
    <title>PicUI - 简洁高效的图床服务</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold text-center mb-8">PicUI 文档</h1>
        <div class="bg-white rounded-lg shadow-md p-6">
            <p class="mb-4">PicUI是一个基于FastAPI开发的现代化图床服务，支持多种图片格式上传、存储和管理。</p>
            <div class="flex justify-center">
                <a href="https://github.com/你的用户名/picui" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded">查看GitHub仓库</a>
            </div>
        </div>
    </div>
</body>
</html>
```

## 步骤7：保护主分支

为了确保代码质量和安全性：

1. 在GitHub仓库页面，点击"Settings" -> "Branches"
2. 在"Branch protection rules"下点击"Add rule"
3. 在"Branch name pattern"输入"main"
4. 选中以下选项：
   - "Require a pull request before merging"
   - "Require approvals"（设置为1或更多）
   - "Require status checks to pass before merging"
   - "Require branches to be up to date before merging"
   - 在状态检查中，选择"Python应用测试"工作流
5. 点击"Create"

## 步骤8：设置自动化集成

### 配置Dependabot进行依赖更新

1. 创建`.github/dependabot.yml`文件：
```bash
mkdir -p .github
nano .github/dependabot.yml
```

2. 添加以下内容：
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
```

### 配置CodeCov进行代码覆盖率分析

1. 注册[CodeCov](https://codecov.io/)账号
2. 将您的GitHub仓库与CodeCov连接
3. 添加`codecov.yml`文件到仓库根目录：
```yaml
codecov:
  require_ci_to_pass: yes

coverage:
  precision: 2
  round: down
  range: "70...100"

  status:
    project:
      default:
        target: auto
        threshold: 5%
    patch:
      default:
        target: auto
        threshold: 10%

comment:
  layout: "reach,diff,flags,files,footer"
  behavior: default
  require_changes: no
```

## 步骤9：创建版本发布

当您的项目达到一个稳定点时：

1. 在本地创建标签并推送：
```bash
git tag -a v1.0.0 -m "第一个正式版本"
git push origin v1.0.0
```

2. 或者在GitHub仓库页面：
   - 点击"Releases" -> "Draft a new release"
   - 创建一个标签（如"v1.0.0"）
   - 填写标题和描述，可以使用Markdown格式
   - 如果需要，上传编译好的文件
   - 点击"Publish release"

## 步骤10：设置自动部署（可选）

如果您想自动部署到云平台，可以配置额外的工作流：

### Railway部署示例

1. 创建`.github/workflows/deploy-railway.yml`文件：
```yaml
name: 部署到Railway

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: 安装Railway CLI
        run: npm install -g @railway/cli
        
      - name: 部署到Railway
        run: railway up
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

2. 在Railway获取API令牌并添加到GitHub Secrets

### Render部署示例

Render支持自动从GitHub部署，只需在Render仪表板中连接您的GitHub仓库即可。

## 文件清单

确保您的仓库包含以下文件：

- `README.md` - 项目说明
- `LICENSE` - MIT许可证文件
- `requirements.txt` - Python依赖列表
- `main.py` - FastAPI应用主文件
- `database.py` - 数据库模型和配置
- `static/` - 静态文件目录
- `uploads/` - 上传文件目录（可能需要在.gitignore中忽略）
- `Dockerfile` - Docker配置
- `.github/workflows/` - GitHub Actions工作流配置
- `.gitignore` - Git忽略文件配置
- `贡献指南.md` - 项目贡献指南
- `服务器部署指南.md` - 服务器部署文档
- `云平台部署指南.md` - 云平台部署文档

## 后续步骤

- 定期更新依赖
- 监控GitHub Actions工作流运行情况
- 关注Issue和Pull Request
- 考虑添加更多自动化测试
- 维护项目文档

恭喜！您的PicUI项目现在已经在GitHub上完全配置好了，包括CI/CD流程和自动化部署！ 