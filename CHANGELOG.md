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

## [1.1.3] - 2026-06-24

### ✨ 新增
- **用户下拉菜单**：顶栏用户名按钮支持 hover 下拉菜单，统一收纳管理服务器、修改个人信息、历史告警、注销等功能
- **个人信息页** (`/profile`)：支持修改用户名和修改密码，修改后强制重新登录
- **管理员专属菜单项**：下拉菜单中"管理后台"和"监控指标"仅管理员可见

### 🔒 安全
- 增强角色权限保护：普通管理员不能降级/删除级别不低于自己的用户
- 初始 admin 账号设为超级管理员 (`super_admin`)，不可被其他管理员降级或删除
- 注销路由支持 POST 方法（配合 CSRF token 更安全）

### 🎨 界面
- 简化登录后页面顶栏：移除冗余按钮，保留公共主页 + 用户下拉菜单
- 移除登录/注册页的深色模式切换按钮
- 修复下拉菜单 hover 间隙问题（鼠标移到菜单上不会闪烁消失）

### 🔧 调整
- 移除管理后台中"修改自己密码"功能（统一走个人信息页）
- 移除管理后台中"为用户添加服务器"功能

## [1.1.2] - 2026-06-24

### 🔒 安全
- 修复非生产环境下默认管理员账号创建问题
- 修复实例绑定 URL 路径不匹配（404 错误）
- 离线服务器延迟显示为 "—" 而非空值

### 🔧 修复
- 修复 flake8 W293 空白行尾随空格警告
- 修复 CI 测试任务配置

## [1.1.1] - 2026-06-23

### 🔧 修复
- 修复 CI 测试作业失败问题
- 调整 flake8 忽略规则与代码库保持一致

## [1.1.0] - 2026-06-21

### ✨ 新增
- 麦块联机 API Key 绑定功能
- 服务器分组管理
- 历史告警页面
- 首次启动自动创建临时管理员账号并打印随机密码

### 🔒 安全
- 多项安全审计漏洞修复
- CSRF 令牌完善
- 会话管理增强

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

[Unreleased]: https://github.com/forgetmelodyXL/mc-monitor/compare/v1.1.3...HEAD
[1.1.3]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.1.3
[1.1.2]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.1.2
[1.1.1]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.1.1
[1.1.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.1.0
[1.0.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.0.0
[0.1.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v0.1.0
