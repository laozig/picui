# GitHub设置指南

本文档将指导您如何将本项目上传到GitHub并进行初始设置。

## 步骤1：创建GitHub账号
如果您还没有GitHub账号，请先在 [GitHub官网](https://github.com/) 注册一个账号。

## 步骤2：创建新仓库
1. 登录到GitHub
2. 点击右上角的"+"图标，然后选择"New repository"
3. 填写仓库名称(例如：picui)
4. 添加可选的描述
5. 保持仓库为"Public"（如果您想让它对所有人可见）
6. 不要初始化仓库（不添加README、.gitignore或LICENSE文件）
7. 点击"Create repository"

## 步骤3：初始化本地仓库并推送到GitHub

打开命令行，在项目目录下运行以下命令：

```bash
# 初始化Git仓库
git init

# 添加所有文件到暂存区
git add .

# 提交更改
git commit -m "初始化提交"

# 添加远程仓库
git remote add origin https://github.com/你的用户名/picui.git

# 推送到主分支
git push -u origin main
```

如果你的默认分支是master而不是main，请使用：
```bash
git branch -M main
git push -u origin main
```

## 步骤4：配置GitHub Actions

GitHub Actions配置文件已经包含在项目中(`.github/workflows/python-app.yml`)。但由于GitHub对隐藏文件夹的处理，您可能需要手动设置：

1. 在GitHub仓库页面中，点击"Actions"选项卡
2. 如果没有自动检测到工作流程，请点击"New workflow"
3. 选择"set up a workflow yourself"
4. 复制本地`python-app.yml`文件的内容到编辑器中
5. 点击"Start commit"，然后点击"Commit new file"

## 步骤5：配置GitHub Pages（可选）

如果您想为项目创建文档网站：

1. 在GitHub仓库页面，点击"Settings"选项卡
2. 滚动到"GitHub Pages"部分
3. 在"Source"下拉菜单中选择"main"分支和"/docs"文件夹（如果您有一个docs文件夹）
4. 点击"Save"

## 步骤6：保护主分支（可选但推荐）

1. 在GitHub仓库页面，点击"Settings"选项卡
2. 点击左侧的"Branches"
3. 在"Branch protection rules"下点击"Add rule"
4. 在"Branch name pattern"输入"main"
5. 选中以下选项：
   - Require pull request reviews before merging
   - Require status checks to pass before merging
   - Require branches to be up to date before merging
6. 点击"Create"

## 步骤7：设置相关集成（可选）

考虑添加以下集成以提升项目质量：

1. [CodeCov](https://codecov.io/) - 代码覆盖率报告
2. [Dependabot](https://github.com/features/security) - 自动依赖更新
3. [Read the Docs](https://readthedocs.org/) - 项目文档托管

## 步骤8：创建版本发布

当您的项目达到一个稳定点时：

1. 在GitHub仓库页面，点击"Releases"
2. 点击"Draft a new release"
3. 创建一个标签（如"v1.0.0"）
4. 填写标题和描述
5. 如果需要，上传编译好的文件
6. 点击"Publish release"

## 文件说明

当您上传代码时，请确保包含以下重要文件：

- `README.md` - 项目说明
- `LICENSE` - 许可证文件
- `CONTRIBUTING.md` - 贡献指南
- 各种配置文件（.gitignore, .gitattributes, Dockerfile等）
- 源代码和文档

恭喜！您的项目现在已经在GitHub上设置好了！ 