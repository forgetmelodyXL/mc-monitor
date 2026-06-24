<div align="center">

# 🎮 MC Server Monitor

**一个开源、零依赖、纯 Python 的 Minecraft 服务器监控面板**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-000000?logo=flask)](https://flask.palletsprojects.com/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#-部署)
[![PWA Ready](https://img.shields.io/badge/PWA-Ready-5A0FC8?logo=pwa)](static/manifest.json)

直接用原生 TCP + Minecraft SLP 协议与服务器通信，**无需任何第三方 API、无需 API Key**。

[功能](#-核心功能) · [快速开始](#-快速开始) · [部署](#-部署) · [截图](#-截图) · [路线图](#-路线图) · [贡献](#-贡献) · [许可证](#-许可证)

</div>

---

## ✨ 核心功能

### 🖥 监控
- **多协议支持** — Java SLP、Bedrock (Raknet)、HTTP(S) 健康检查、通用 TCP
- **后台轮询** — APScheduler 定时采集（默认 60 秒），写入 `status_logs` 历史表
- **掉线/恢复告警** — 自动检测状态切换，弹窗告警 + 历史记录
- **历史图表** — Chart.js 双 Y 轴折线图（在线人数 + 延迟）
- **服务器分组** — 多分组管理，每个服务器可归属一个分组
- **搜索 + 状态筛选** — 客户端即时过滤

### 🔐 安全
- **CSRF 保护** — 所有非 GET 请求验证一次性 token
- **Rate Limiting** — 登录、API、添加服务器等多类令牌桶限流
- **密码安全** — PBKDF2-HMAC-SHA256 + 随机盐，20 万次迭代
- **会话管理** — Flask 签名 Cookie，HttpOnly + SameSite=Lax，7 天有效期
- **角色权限** — 超级管理员 / 管理员 / 版主 / 普通用户四级权限体系

### 🛠 管理
- **管理后台** — 用户管理、服务器管理、注册开关、维护模式
- **数据清理策略** — 可配置 `status_logs` / `alerts` 保留天数 + 手动清理
- **多用户** — 每个用户独立管理自己的服务器
- **公开 / 私有** — 选择性公开到公共主页
- **麦块联机 API 代理** — 集成麦块（minekuai）查询接口
- **个人中心** — 修改用户名、修改密码，修改后强制重新登录

### 🌐 体验
- **深色模式** — 跟随系统 / 手动切换，localStorage 持久化
- **PWA** — `manifest.json` + Service Worker，可安装到桌面/主屏
- **响应式布局** — 桌面、平板、手机自适应
- **错误页** — 自定义 404 / 403 / 500 页面
- **数据库迁移** — 自动 schema 版本管理（`schema_versions` 表）

---

## 📸 截图

> 截图占位 — 实际截图请放入 `docs/screenshots/` 后引用

| Dashboard | 告警历史 | 管理后台 |
|:---:|:---:|:---:|
| 监控卡片 + 图表 | 时间线 + 筛选 | 用户/服务器管理 |

---

## 🚀 快速开始

### 方式一：Windows 一键启动（推荐）

1. 进入 [ Releases 页面](https://github.com/forgetmelodyXL/mc-monitor/releases/latest) 下载最新版的 `mcmonitor.exe`
2. 双击运行 `mcmonitor.exe`
3. 浏览器自动打开 `http://127.0.0.1:5000`

> 💡 单文件 EXE，**无需安装 Python**，复制到任何 Windows 10/11 机器即可运行。

### 方式二：手动 Python 环境

```bash
# 1. 克隆仓库
git clone https://github.com/forgetmelodyXL/mc-monitor.git
cd mc-monitor

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
python main.py
# 或
python app.py
```

### 方式三：手动构建 EXE（开发用）

```bash
# 在开发机上
build.bat
# 输出：dist\mcmonitor.exe
```

---

## 👤 默认管理员账号

首次启动时，系统会**自动创建临时管理员账号**，并在控制台输出随机密码：

```
============================================================
  [MC-Monitor] 首次启动，已自动创建临时管理员账号
  用户名: admin
  密  码: xxxxxxxxxxxx
============================================================
```

> ⚠️ **首次登录后请立即修改密码！** 进入下拉菜单 →「修改个人信息」→ 修改密码。

> 💡 如果忘记密码，删除 `mcmonitor.db` 后重启，会重新生成临时管理员账号。

---

## 📖 使用说明

### 公共主页（无需登录）
访问 `/` 查看所有**公开**的 MC 服务器，显示在线状态、玩家数、版本、延迟、MOTD。

### 我的管理（登录后）
- 添加服务器：名称、主机/IP、端口、协议
- 公开 / 私有切换
- 立即刷新、查看历史图表
- 点击右上角用户名展开下拉菜单：管理服务器、修改个人信息、历史告警、注销

### 个人中心
- 修改用户名（修改后需重新登录）
- 修改密码（修改后需重新登录）

### 管理后台（仅管理员）
- 用户列表：重置密码、升级/降级管理员、删除用户
- 服务器列表：编辑/删除任意用户的服务器
- 全局设置：注册开关、维护模式、数据清理、麦块联机 API 配置

> 🔒 **超级管理员保护**：初始 `admin` 账号为超级管理员，不可被其他管理员降级或删除。

---

## 🌐 部署

### 监听公网

默认 `app.run(host="0.0.0.0", port=5000)`，局域网 + 公网都可达。

```powershell
# Windows 防火墙
netsh advfirewall firewall add rule name="MC Monitor" dir=in action=allow protocol=TCP localport=5000
```

> 云服务商（阿里云/腾讯云/AWS）还需在控制台安全组放行 5000 端口。

### Linux 部署（systemd 示例）

```ini
# /etc/systemd/system/mc-monitor.service
[Unit]
Description=MC Server Monitor
After=network.target

[Service]
User=mcmonitor
WorkingDirectory=/opt/mc-monitor
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now mc-monitor
```

### 反向代理（Nginx + HTTPS）

```nginx
server {
    listen 443 ssl;
    server_name mc.example.com;

    ssl_certificate     /etc/letsencrypt/live/mc.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mc.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 🧠 技术栈

| 类别 | 技术 |
|------|------|
| **后端** | Python 3.10+ · Flask 3 · SQLite (WAL) |
| **协议** | Minecraft SLP · Bedrock (Raknet) · HTTP(S) · TCP |
| **调度** | APScheduler (BackgroundScheduler) |
| **前端** | Jinja2 · 原生 CSS · Chart.js 4.4 (CDN) |
| **PWA** | manifest.json + Service Worker (Network First) |
| **打包** | PyInstaller (单文件 EXE) |

### 架构

```
app.py            # Flask 主程序（路由 / SLP / DB / CSRF / 告警 / 迁移）
main.py           # 启动入口（含 sys._MEIPASS 处理）
templates/        # HTML 模板
static/           # CSS / PWA manifest / Service Worker
requirements.txt  # Python 依赖
```

### 数据库

SQLite 单文件 `mcmonitor.db`，自动迁移（`schema_versions` 表）。表结构：

- `users` — 用户账号
- `servers` — 监控服务器
- `server_groups` — 服务器分组
- `status_logs` — 每次轮询的历史记录
- `alerts` — 掉线/恢复告警
- `settings` — 全局开关

---

## ❓ 常见问题

**Q: 测试服务器一直显示离线？**
> 1) 确认地址和端口（默认 25565）
> 2) 用 `telnet host port` 测试连通性
> 3) 服务器防火墙是否允许入站
> 4) Java 版选 `slp` 协议，基岩版选 `bedrock`

**Q: 忘了管理员密码？**
> 删掉 `mcmonitor.db` 后重启，会自动生成新的临时管理员账号（密码打印在控制台）。

**Q: 数据库在哪里？**
> 项目根目录下的 `mcmonitor.db`，直接拷贝即可完整迁移。

**Q: 如何迁移到新服务器？**
> 1) 复制整个项目文件夹（或部署代码 + `pip install -r requirements.txt`）
> 2) 复制 `mcmonitor.db` 到新机器
> 3) 启动即可

**Q: launch.bat 卡在下载 Python？**
> 手动从 https://www.python.org/downloads/windows/ 下载嵌入式版（`python-3.x.x-embed-amd64.zip`）解压到 `runtime\`，再运行 `launch.bat`。

---

## 🛡 安全建议

1. **修改默认 admin 密码** — 这是最重要的第一步
2. **不要把 `mcmonitor.db` 暴露到公网**（数据库包含密码哈希）
3. **公网部署务必配置 HTTPS**（推荐 Nginx + Let's Encrypt）
4. **使用防火墙白名单**限制管理后台访问
5. **定期备份** `mcmonitor.db`

---

## 🗺 路线图

- [x] 多协议支持（Java/Bedrock/HTTP/TCP）
- [x] 历史图表
- [x] 掉线/恢复告警
- [x] 深色模式
- [x] PWA
- [x] 数据库迁移
- [ ] Telegram / 微信 / 邮件告警推送
- [ ] 多语言（i18n）
- [ ] Docker 镜像
- [ ] WebSocket 实时状态推送

---

## 🤝 贡献

欢迎 PR 和 Issue！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交改动 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

详细规范见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 📜 许可证

本项目基于 [MIT License](LICENSE) 开源。

Copyright © 2024–2026 MC Server Monitor Contributors

---

## 🙏 致谢

- [wiki.vg](https://wiki.vg/Server_List_Ping) — Minecraft SLP 协议文档
- [Chart.js](https://www.chartjs.org/) — 图表库
- [Flask](https://flask.palletsprojects.com/) — Web 框架
- [APScheduler](https://apscheduler.readthedocs.io/) — 任务调度

---

<div align="center">

如果这个项目对你有帮助，欢迎 ⭐ Star！

[报告 Bug](https://github.com/forgetmelodyXL/mc-monitor/issues) · [请求功能](https://github.com/forgetmelodyXL/mc-monitor/issues) · [讨论](https://github.com/forgetmelodyXL/mc-monitor/discussions)

</div>
