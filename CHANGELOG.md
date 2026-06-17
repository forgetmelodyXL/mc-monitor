# 更新日志

本项目的所有重要变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中
- Telegram / 微信 / 邮件告警推送
- WebSocket 实时状态推送
- Docker 镜像
- 多语言（i18n）

## [1.0.0] - 2026-06-17

### ✨ 新增
- **多协议支持**：Java SLP、Bedrock (Raknet)、HTTP(S) 健康检查、通用 TCP
- **后台定时轮询**：APScheduler 默认 60s 采集一次
- **历史图表**：Chart.js 双 Y 轴折线图（在线人数 + 延迟）
- **掉线/恢复告警**：状态切换自动告警 + 历史告警页（`/alerts`）
- **服务器分组**：`server_groups` 表 + 分组管理 UI
- **搜索 + 状态筛选**：客户端即时过滤
- **CSRF 保护**：自定义实现，一次性 token
- **Rate Limiting**：令牌桶实现，按 IP + 类别限流
- **数据自动清理策略**：可配置 `status_logs` / `alerts` 保留天数
- **深色模式**：CSS 变量 + `localStorage` 持久化
- **PWA 支持**：`manifest.json` + Service Worker
- **数据库迁移系统**：`schema_versions` 表 + 自动迁移
- **自定义错误页**：404 / 403 / 500
- **管理后台**：用户/服务器管理、注册开关、维护模式
- **麦块联机 API 代理**

### 🔒 安全
- PBKDF2-HMAC-SHA256 密码哈希（20 万次迭代 + 随机盐）
- HttpOnly + SameSite=Lax Cookie
- 7 天会话有效期
- 登录/注册速率限制

### 📦 部署
- 一键启动脚本 `launch.bat`（自动下载便携 Python）
- PyInstaller 单文件打包 `build.bat`
- Linux systemd 服务示例
- Nginx + HTTPS 反向代理示例

### 📝 文档
- 重写 `README.md`（特性、部署、FAQ）
- 新增 `CONTRIBUTING.md`
- 新增 `CHANGELOG.md`

## [0.1.0] - 2025-XX-XX

### 初始版本
- 基础 Flask + SQLite 用户系统
- Minecraft SLP 协议实现
- 公共主页 + 我的管理
- 简单管理后台

[Unreleased]: https://github.com/forgetmelodyXL/mc-monitor/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.0.0
[0.1.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v0.1.0
