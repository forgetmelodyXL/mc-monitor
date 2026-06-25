# 邮箱注册与显示名称 Spec

## Why
当前注册使用任意用户名，无法与邮件系统关联。需要改为邮箱注册，支持显示名称，并优化管理员重置密码流程。

## What Changes
- 注册方式改为邮箱账号注册，用户名字段改为邮箱
- 新增 `display_name` 字段（可选、唯一），在个人资料页设置
- 公共主页服务器归属显示：优先显示 display_name，未设置则显示邮箱
- 管理后台重置密码按钮改为弹窗确认，根据邮件功能状态决定发送邮件或重置为默认密码
- 新增管理开关：注册时是否发送邮件通知（依赖邮件功能已开启）

## Impact
- Affected specs: 无
- Affected code: `app.py`（注册、登录、profile、admin、public API）、`templates/register.html`、`templates/login.html`、`templates/profile.html`、`templates/admin.html`、`templates/index.html`、`db.py`（迁移）

## ADDED Requirements

### Requirement: 邮箱注册
系统 SHALL 要求用户使用邮箱作为账号进行注册。

#### Scenario: 注册成功
- **WHEN** 用户填写有效邮箱和密码并提交注册
- **THEN** 系统创建用户（username 字段存储邮箱），注册成功

#### Scenario: 邮箱格式无效
- **WHEN** 用户填写非邮箱格式的账号名
- **THEN** 系统提示"请输入有效的邮箱地址"

#### Scenario: 邮箱已被注册
- **WHEN** 用户填写的邮箱已被其他用户使用
- **THEN** 系统提示"该邮箱已被注册"

### Requirement: 显示名称（display_name）
系统 SHALL 允许用户在个人资料页设置可选的显示名称，不可与其他用户重复。

#### Scenario: 设置显示名称成功
- **WHEN** 用户在个人资料页填写未使用的显示名称并提交
- **THEN** 系统保存 display_name，提示设置成功

#### Scenario: 显示名称重复
- **WHEN** 用户填写的显示名称已被其他用户使用
- **THEN** 系统提示"该用户名已被占用"

#### Scenario: 显示名称未设置
- **WHEN** 用户未设置 display_name
- **THEN** 系统在公开显示中使用邮箱（脱敏处理：@ 前保留 3 位 + ***）

### Requirement: 公共主页归属显示
公共主页服务器卡片 SHALL 优先显示用户设置的 display_name，未设置时显示邮箱（脱敏）。

#### Scenario: 用户已设置 display_name
- **WHEN** 公开服务器归属于已设置 display_name 的用户
- **THEN** 页面显示"由 [display_name] 公开"

#### Scenario: 用户未设置 display_name
- **WHEN** 公开服务器归属于未设置 display_name 的用户
- **THEN** 页面显示"由 [脱敏邮箱] 公开"

### Requirement: 管理后台重置密码优化
管理后台重置密码功能 SHALL 移除手动输入密码框，改为弹窗确认后自动处理。

#### Scenario: 邮件功能已开启
- **WHEN** 管理员点击重置密码并确认，且邮件功能已开启
- **THEN** 系统向目标用户邮箱发送重置密码邮件，密码重置为随机 8 位字符

#### Scenario: 邮件功能未开启
- **WHEN** 管理员点击重置密码并确认，且邮件功能未开启
- **THEN** 系统将目标用户密码重置为 `123456789`

#### Scenario: 目标用户无邮箱
- **WHEN** 管理员重置密码，但目标用户无邮箱记录
- **THEN** 系统将密码重置为 `123456789`

### Requirement: 注册邮件通知开关
管理后台 SHALL 提供"注册邮件通知"开关，控制新用户注册后是否发送欢迎邮件。

#### Scenario: 开启注册邮件通知
- **WHEN** 管理员开启注册邮件通知（需邮件功能已开启）
- **THEN** 新用户注册成功后收到欢迎邮件

#### Scenario: 关闭注册邮件通知
- **WHEN** 管理员关闭注册邮件通知
- **THEN** 新用户注册后不发送邮件

#### Scenario: 邮件功能未开启时无法开启
- **WHEN** 邮件功能未开启，管理员尝试开启注册邮件通知
- **THEN** 系统提示"请先开启邮件功能"

## MODIFIED Requirements

### Requirement: 注册页面
注册页面 SHALL 将用户名输入框改为邮箱输入框，并添加邮箱格式验证。

### Requirement: 登录页面
登录页面 SHALL 将用户名标签改为"邮箱"。

### Requirement: 个人资料页
个人资料页 SHALL 新增"设置显示名称"区域，允许用户设置/修改 display_name。

### Requirement: 管理后台用户列表
管理后台用户列表 SHALL 移除重置密码的新密码输入框，保留重置密码按钮，点击后弹出二次确认对话框。

## REMOVED Requirements

### Requirement: 旧重置密码表单
**Reason**: 管理员手动输入新密码不安全且繁琐
**Migration**: 后端自动生成密码并通过邮件发送或设为默认值