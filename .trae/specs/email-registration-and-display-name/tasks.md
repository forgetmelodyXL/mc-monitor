# Tasks

- [x] Task 1: 数据库迁移 — 添加 display_name 列和注册邮件通知设置
  - [x] 在 `_run_migrations` 中新增 v7 迁移，为 users 表添加 `display_name TEXT` 列
  - [x] 在 `_ensure_schema` 的 col_sql 中添加 `ALTER TABLE users ADD COLUMN display_name TEXT`
  - [x] 将 `_SCHEMA_VERSION` 升级到 7
  - [x] 在 settings 中初始化 `registration_email_enabled` 默认值为 "0"

- [x] Task 2: 注册页面改造为邮箱注册
  - [x] 修改 `register.html`：用户名输入框改为邮箱输入框（type="email"），标签改为"邮箱"
  - [x] 修改 `register()` 路由：添加邮箱格式验证，校验 `@` 和 `.` 存在
  - [x] 保持已有的密码长度、确认密码逻辑不变

- [x] Task 3: 登录页面标签更新
  - [x] 修改 `login.html`：登录输入框标签改为"邮箱"

- [x] Task 4: 个人资料页新增显示名称设置
  - [x] 修改 `profile.html`：新增"设置显示名称"区域，包含输入框和提交按钮
  - [x] 修改 `user_profile()` 路由：新增 `action=change_display_name` 处理逻辑
  - [x] 校验 display_name 长度 3-32 字符，唯一性检查
  - [x] 更新 session 中的 display_name

- [x] Task 5: 公共主页归属显示优化
  - [x] 修改 `public_status()` API：查询时 JOIN users 获取 display_name 和 email（username）
  - [x] 返回 `owner_display` 字段：优先 display_name，否则脱敏邮箱
  - [x] 修改 `index.html`：`owner_name` 改为优先 display_name 显示
  - [x] 同时修改 `admin_panel()` 中的 servers 查询（保持一致性）

- [x] Task 6: 管理后台重置密码改造
  - [x] 修改 `admin.html`：移除重置密码表单中的密码输入框，保留按钮
  - [x] 添加 JavaScript 确认弹窗逻辑（`confirm()` 对话框）
  - [x] 修改 `admin_reset_password()` 路由：移除 admin_password 验证、new_password 输入
  - [x] 检查邮件功能是否开启 + 目标用户是否有邮箱
  - [x] 邮件开启时：生成随机密码，更新数据库，发送邮件通知
  - [x] 邮件未开启或无邮箱时：密码重置为 `123456789`

- [x] Task 7: 注册邮件通知开关
  - [x] 修改 `admin.html`：在邮件告警配置区域新增"注册邮件通知"开关
  - [x] 修改 `admin_email_settings()` 路由：保存 `registration_email_enabled` 设置
  - [x] 修改 `register()` 路由：注册成功后检查 `registration_email_enabled` 和 `email_enabled`，发送欢迎邮件
  - [x] 修改 `admin_panel()` 路由：传递 `registration_email_enabled` 到模板

# Task Dependencies
- Task 2, 3, 4, 5, 6, 7 均依赖 Task 1（数据库迁移）
- Task 5 依赖 Task 4（display_name 功能）
- Task 7 依赖 Task 2（注册流程）
- Task 2, 3, 6 可并行开发