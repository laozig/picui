# PicUI GitHub 配置指南

本文档提供 PicUI 项目在 GitHub 上的配置说明，包括工作流设置和自动化部署。

## GitHub Actions 配置

PicUI 项目使用 GitHub Actions 进行自动化测试、构建和部署。配置文件位于 `.github/workflows/python-app.yml`。

### 主要功能

1. **自动化测试**：在多个 Python 版本上运行测试
2. **代码质量检查**：使用 flake8 进行代码风格检查
3. **Docker 镜像构建**：自动构建并测试 Docker 镜像
4. **生产环境部署**：在测试通过后部署到生产环境

### 配置说明

在使用 GitHub Actions 之前，需要在仓库的 Settings > Secrets and variables > Actions 中设置以下密钥：

| 密钥名称 | 描述 |
|---------|------|
| `DOCKER_USERNAME` | Docker Hub 用户名 |
| `DOCKER_PASSWORD` | Docker Hub 密码或访问令牌 |
| `SERVER_HOST` | 部署服务器地址 |
| `SERVER_USER` | 服务器用户名 |
| `SERVER_KEY` | SSH 私钥 |
| `SERVER_PASSPHRASE` | SSH 私钥密码（如有） |
| `SLACK_WEBHOOK` | Slack 通知 Webhook URL |
| `PYPI_API_TOKEN` | PyPI 发布令牌 |

## 仓库设置指南

### 1. 分支保护

为保护主分支代码质量，建议设置分支保护规则：

1. 进入仓库 Settings > Branches
2. 点击 "Add rule" 添加规则
3. 在 "Branch name pattern" 中输入 `main`
4. 勾选 "Require pull request reviews before merging"
5. 勾选 "Require status checks to pass before merging"
6. 勾选 "Require branches to be up to date before merging"
7. 在 "Status checks" 中选择 "test" 和 "build" 工作流

### 2. 问题模板

为规范化问题报告，添加问题模板：

1. 在项目根目录创建 `.github/ISSUE_TEMPLATE/` 目录
2. 添加 `bug_report.md` 和 `feature_request.md` 模板文件

### 3. Pull Request 模板

创建 `.github/pull_request_template.md` 文件，规范 PR 提交格式。

## 自动化部署流程

当代码推送到 `main` 分支且通过所有测试后，GitHub Actions 会自动：

1. 构建最新 Docker 镜像
2. 推送镜像到 Docker Hub
3. 连接到部署服务器
4. 拉取最新镜像并重启服务

## 常见问题解决

### 工作流执行失败

1. 检查是否正确设置了所需的 Secrets
2. 查看日志了解具体错误
3. 确保测试用例全部通过

### Docker 构建问题

1. 验证 Dockerfile 语法
2. 确认 Docker Hub 凭据正确
3. 检查镜像构建步骤日志 