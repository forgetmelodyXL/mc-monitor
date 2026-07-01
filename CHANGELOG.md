# 更新日志

本项目的所有重要变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.6.3] - 2026-06-27

### ✨ 新增
- **PJAX 无刷新页面加载**：所有页面支持 PJAX 导航，点击链接无整页刷新，顶部进度条动画，浏览器前进/后退正常
- **共享布局模板**：提取 `layout.html` 统一管理顶栏、暗色模式、Toast 通知、PWA 注册，消除约 500 行重复代码

### 🎨 优化
- 图表功能改为在每个服务器行下方直接显示，不再全部堆在页面底部
- 6 个页面模板全部重构为继承 `layout.html`，结构更清晰

### 🔧 修复
- 修复 PJAX 导航后卡片间距消失（嵌套 `<main>` 导致 `gap` 失效）
- 修复公共主页 PJAX 刷新后样式错乱（重复 `<main class="container">` 嵌套）

## [1.6.2] - 2026-06-27

### ✨ 新增
- **历史告警时间范围查询**：新增开始日期和结束日期筛选，支持按时间段查询服务器掉线/恢复告警
- **历史告警统计卡片重构**：顶部统计改为与监控指标一致的 `stats-row` 样式，包含告警总数、掉线告警、恢复通知三张卡片

### 🎨 优化
- 麦块控制命令输出简化为「[COMMAND] ✅ 发送成功 / ❌ 发送失败」格式，与电源按钮风格一致
- 历史告警页面移除已读/未读状态概念，界面更简洁
- 全部 Python 文件通过 flake8 代码风格检查（max-line-length=120）

### 🔧 修复
- 修复历史告警分页跳转时筛选条件丢失问题（类型筛选 + 时间范围均保留）

## [1.6.0] - 2026-06-26

### ✨ 新增
- **后台角色管理弹窗**：设置用户角色改为弹窗操作，支持选择角色后确认，操作后刷新页面并显示顶部提示
- **邮件告警 Toggle 开关**：邮件告警配置和注册邮件通知改为滑动开关，点击自动保存
- **SMTP 密码明文显示**：管理后台 SMTP 密码字段持久化明文显示，不再星号隐藏
- **排序弹窗**：服务器列表新增「修改排序」按钮，弹窗内通过 ▲▼ 按钮调整顺序（替代拖拽）
- **服务器 ID 列**：仪表盘服务器列表新增独立 ID 列，显示在名称前面
- **服务器名称唯一性**：服务器名称全局唯一（同一 IP 可被多个用户绑定，但名称不能重复）
- **服务器 Host 验证**：Server Host 必须是有效的域名或 IP 地址
- **服务器名称中文限制**：名称至少 2 个中文字符，最多 8 个中文字符
- **名称长度按显示宽度计算**：1 个中文字符 = 2 宽度，1 个英文字符 = 1 宽度，范围 4-16 宽度

### 🎨 优化
- 所有页面顶栏用户名统一显示为「用户名 · 角色」格式
- 测试邮件按钮移至保存配置下方
- 排序保存后自动刷新页面，顶部居中横幅提示反馈
- 系统时间统一使用中国北京时间
- 删除服务器/分组使用主题一致的自定义确认弹窗，替代浏览器原生 confirm()
- 麦块控制命令反馈简化为「✅ 发送成功 / ❌ 发送失败」，去除 HTTP 状态码
- 顶部 flash 横幅改用纯 CSS keyframe 动画实现自动消失，避免动画冲突

### 🔧 修复
- 修复角色弹窗确认按钮无反应（`csrf_token` 字段名应为 `_csrf_token`）
- 修复旧版本数据库绑定麦块实例时报 `Failed to fetch`（缺少 `minekuai_instance_id` 列，`get_db()` 自动执行 schema 迁移）
- 修复拖拽排序始终不生效的问题（改为排序弹窗方案）
- 修复 toast 与 flash 横幅重复显示问题（AJAX 返回 JSON 不设 flash，表单提交用 flash）

## [1.5.0] - 2026-06-26

### ✨ 新增
- **统一输入框样式**：所有输入框（text/email/password/number/tel/url/search/date/time/select/textarea）使用统一的设计风格
- **自定义 Select 箭头**：下拉框使用 SVG 自定义箭头，替换原生丑陋样式
- **浏览器自动填充修复**：修复 Chrome 自动填充后的黄色背景问题
- **旧数据库自动兼容**：`get_db()` 自动执行 schema 迁移，确保旧版本数据库可以正常使用所有功能

### 🔧 修复
- 修复 `getCsrfToken()` 函数在 `dashboard.html` 中未定义的 JS 错误
- 修复 `get_db()` 在非请求上下文（初始化、CLI）下调用失败的问题
- 修复 flake8 F823/F541 错误及多个未使用变量警告

### 🎨 优化
- 移除开发/生产环境区分，统一使用 Waitress 生产级服务器
- 删除 `MCMONITOR_ENV` 环境变量
- 统一日志配置：仅输出到文件，Werkzeug 日志级别为 WARNING
- 删除自动打开浏览器功能（`MCMONITOR_NOBROWSER`）
- 完善 `.gitignore`，移除本地 IDE 配置目录 `.trae/`
- 所有输入框添加 hover/focus/disabled 状态
- number 输入框去除默认上下箭头
- 复选框/单选框使用主题色高亮
- 暗色模式下所有输入框样式完整支持

## [1.4.0] - 2026-06-25

### ✨ 新增
- **注册方式重构**：注册需填写用户名（3-32 字符）、邮箱、密码（8 位以上），用户名和邮箱均唯一
- **双模式登录**：支持用户名+密码 或 邮箱+密码两种方式登录
- **个人资料页重构**：左侧按钮菜单 + 右侧内容区布局，支持修改个人资料和配置告警邮箱
- **AJAX 保存反馈**：个人资料页保存按钮使用 AJAX 提交，带 Toast 通知和加载动画
- **全局按钮反馈**：所有页面的保存/提交按钮点击时显示加载状态，防止重复提交
- **全局 Toast 通知**：所有页面的 flash 消息自动转为右上角 Toast 通知
- **超级管理员机制**：有且仅有一个超级管理员，拥有完全权限，任何人无权创建第二个超级管理员

### 🔧 修复
- 修复首次运行检测方式：从检测"是否有任何用户"改为检测"是否有超级管理员"
- 移除所有对 `username == 'admin'` 的硬编码判断，改为基于 `role` 的判断
- 修复 admin/dashboard/alerts/metrics/index 页面 flash 消息被消费但未渲染的 bug

### 🎨 优化
- 下拉菜单「修改个人信息」统一改为「个人资料」，并移至下拉菜单第一项
- 管理后台角色选择下拉框移除超级管理员选项（超级管理员唯一，不可创建）

## [1.3.2] - 2026-06-25

### 🔧 修复
- 修复打包 EXE 进入修改个人资料页面报 500 错误（`session.is_admin` 属性访问改为字典访问）
- 修复旧数据库缺失 `email` / `email_alert_enabled` / `email_cooldown` 列导致 `OperationalError`
- 修复 `_run_migrations` 数据库迁移系统从未被调用，导致后续 schema 变更不生效

## [1.3.1] - 2026-06-25

### 🔧 修复
- 修复生产环境 HTTP 访问时 Session Cookie 丢失，导致登录始终 403（`SESSION_COOKIE_SECURE = False`）

## [1.3.0] - 2026-06-25

### ✨ 新增
- **命令行工具（CLI）**：新增 `monitor` 前缀指令，支持重置 admin 密码、创建用户、列出用户等后台管理操作
- **交互式命令行**：服务运行时可直接在控制台输入 `monitor` 命令进行管理，无需重启程序
- **WAL 自动清理**：服务启动时自动 checkpoint 上次遗留的 WAL 文件，直接叉掉窗口也不会残留脏数据

### 🎨 优化
- **首次启动信息**：admin 账号密码信息移到启动横幅下方统一展示，更醒目
- **热加载模式**：debug 模式下父进程（监控进程）不再重复打印启动信息，输出更清爽
- **WAL 配置**：设置 `wal_autocheckpoint = 1000`，运行中自动合并，避免 WAL 文件无限增长

## [1.2.0] - 2026-06-25

### ✨ 新增
- **Docker 部署支持**：新增 `Dockerfile` 和 `docker-compose.yml`，支持容器化部署
- **Linux 一键安装脚本**：`install.sh` / `update.sh` / `uninstall.sh`，自动检测环境并安装依赖（Docker 或 Python）
- **自动安装依赖**：一键脚本支持自动安装 Docker、Python3、git，支持 Debian / RHEL / Arch / Alpine 等主流发行版
- **systemd 自动配置**：Python 方式部署可选配置 systemd 服务，实现开机自启
- **邮件告警推送**：管理员可在后台配置 SMTP，用户在个人中心开启后，服务器上下线时自动收到邮件通知（带冷却机制，防骚扰）
- **邮件测试功能**：管理后台支持发送测试邮件验证 SMTP 配置

### 🔧 调整
- **简化环境变量**：移除 `MCMONITOR_BOOTSTRAP_ADMIN` 和 `MCMONITOR_BOOTSTRAP_USERNAME`，仅通过 `MCMONITOR_BOOTSTRAP_PASSWORD` 控制初始管理员创建（用户名固定为 `admin`）
- **Session 密钥**：生产环境未设置 `MCMONITOR_SECRET_KEY` 时自动生成，与开发环境行为一致
- **默认配置优化**：生产环境下 `MCMONITOR_NOBROWSER` 默认为 `1`（不自动打开浏览器）

### 计划中
- Telegram / 微信 / 钉钉告警推送
- WebSocket 实时状态推送
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

[Unreleased]: https://github.com/forgetmelodyXL/mc-monitor/compare/v1.3.2...HEAD
[1.3.2]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.3.2
[1.3.1]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.3.1
[1.3.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.3.0
[1.2.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.2.0
[1.1.3]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.1.3
[1.1.2]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.1.2
[1.1.1]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.1.1
[1.1.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.1.0
[1.0.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v1.0.0
[0.1.0]: https://github.com/forgetmelodyXL/mc-monitor/releases/tag/v0.1.0
