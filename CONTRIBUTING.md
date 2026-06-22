# 贡献指南

感谢你考虑为本项目做出贡献！🎉

## 🐛 报告 Bug

提交 Issue 前请：

1. 搜索现有 Issue，避免重复
2. 使用 Bug Report 模板（[`.github/ISSUE_TEMPLATE/bug_report.md`](.github/ISSUE_TEMPLATE/bug_report.md)）
3. 包含：
   - 操作系统 + Python 版本
   - 复现步骤
   - 预期行为 vs 实际行为
   - 截图 / 错误日志（如有）

## ✨ 提议新功能

1. 先开 Issue 讨论，避免做出来不符合项目方向
2. 使用 Feature Request 模板
3. 说明：
   - 这个功能解决什么问题
   - 目标用户是谁
   - 是否已有替代方案

## 🔧 提交 Pull Request

### 开发流程

```bash
# 1. Fork 后克隆
git clone https://github.com/<your-name>/mc-monitor.git
cd mc-monitor

# 2. 创建特性分支
git checkout -b feature/awesome-feature

# 3. 设置开发环境
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 4. 启动开发服务器
python main.py
# 服务器运行在 http://127.0.0.1:5000
```

### 代码规范

- **Python**：遵循 [PEP 8](https://peps.python.org/pep-0008/)
- **Jinja2 模板**：缩进 4 空格
- **CSS**：保持 `static/style.css` 现有风格，BEM 命名
- **提交信息**：使用 [Conventional Commits](https://www.conventionalcommits.org/)

```
feat: 添加服务器分组功能
fix: 修复登录时 CSRF token 验证失败
docs: 更新 README 部署章节
refactor: 重构 rate limit 模块
test: 为 ping_server 添加单元测试
```

### 提交前检查

- [ ] 代码无语法错误（`python -m py_compile app.py main.py`）
- [ ] 启动后能正常访问首页
- [ ] 没有引入新依赖到 `requirements.txt`（除非必要）
- [ ] 没有提交数据库文件、缓存、敏感信息
- [ ] 提交信息清晰描述了改动

## 📁 项目结构

```
mc-monitor/
├── app.py                  # Flask 主程序
├── main.py                 # 启动入口
├── requirements.txt        # 依赖
├── launch.bat              # Windows 启动
├── build.bat               # PyInstaller 打包
├── regenerate_bats.py      # .bat 模板
├── templates/              # Jinja2 模板
│   ├── base.html
│   ├── dashboard.html
│   ├── admin.html
│   └── ...
├── static/                 # 静态资源
│   ├── style.css
│   ├── manifest.json       # PWA
│   └── sw.js               # Service Worker
└── docs/                   # 文档（可选）
```

## 🔒 安全问题

**请勿**通过公开 Issue 报告安全漏洞。请私下联系维护者：`<815521655@qq.com>`

## 📜 许可

提交 PR 即表示你同意你的代码以 [MIT License](LICENSE) 授权。

---

再次感谢你的贡献！💖
