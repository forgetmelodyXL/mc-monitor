# MC-Monitor 安全审计修复 - 实施计划

## [x] Task 1: 修复硬编码 SECRET_KEY（VULN-0001）
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 移除源码中硬编码的默认密钥回退逻辑
  - 生产环境未设置 `MCMONITOR_SECRET_KEY` 时应用拒绝启动并抛出错误
  - 开发模式生成随机密钥用于测试
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: 生产模式下未设置密钥，启动时抛出 `RuntimeError`
  - `programmatic` TR-1.2: 开发模式下自动生成随机密钥，应用正常启动
- **Notes**: 修改 `app.py` 第 90-101 行

## [x] Task 2: 修复 Minekuai instance_id API 路径注入（VULN-0004）
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 在绑定端点 `/server/{id}/bind-instance` 对 `instance_id` 实施正则校验（仅允许字母、数字、下划线、连字符）
  - 在所有 Minekuai API 调用端点（power、command、resources）双重校验 `instance_id`
  - 拒绝包含 `../`、`..\\`、`@`、`:` 的输入
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: 提交包含 `../` 的 `instance_id` 返回 400 错误
  - `programmatic` TR-2.2: 提交纯字母数字的 `instance_id` 正常处理
- **Notes**: 修改 `app.py` 第 2486-2487 行及 `_get_server_for_minekuai` 函数

## [x] Task 3: 修复管理员密码重置无需凭证验证（VULN-0005）
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 在 `/admin/users/{user_id}/reset-password` 路由中要求管理员提供当前密码
  - 验证管理员当前密码正确后才允许重置
  - 从 Flash 消息中移除明文密码输出
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `human-judgment` TR-3.1: 未提供管理员密码时，密码重置被拒绝
  - `human-judgment` TR-3.2: Flash 消息中不显示明文密码
- **Notes**: 修改 `app.py` 第 1460-1479 行

## [x] Task 4: 修复 API 与 Minekuai 路由 CSRF 保护绕过（VULN-0003）
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 移除 `ensure_csrf_token()` 中对 `/api/` 和 `/minekuai/` 路由的 blanket 跳过逻辑
  - 对 AJAX 请求支持通过 `X-CSRF-Token` 自定义头部传输令牌
  - 更新前端 JavaScript 代码，在所有 AJAX POST 请求中携带 CSRF 令牌
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: 无 CSRF 令牌的 POST 请求到 `/api/alerts/acknowledge` 返回 403
  - `programmatic` TR-4.2: 携带有效 CSRF 令牌的请求正常处理
- **Notes**: 修改 `app.py` 第 428-444 行及前端模板中的 AJAX 请求代码

## [x] Task 5: 修复登录 next 参数开放重定向（VULN-0002）
- **Priority**: P1
- **Depends On**: None
- **Description**: 
  - 使用 `urllib.parse.urlparse()` 解析 `next` 参数
  - 拒绝任何包含 `netloc`（主机名）或 `scheme`（协议）的 URL
  - 拒绝协议相对 URL（如 `//evil.com`）
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-5.1: `next=//evil.com` 被拒绝，重定向到默认页面
  - `programmatic` TR-5.2: `next=http://evil.com` 被拒绝，重定向到默认页面
  - `programmatic` TR-5.3: `next=/dashboard` 正常跳转
- **Notes**: 修改 `app.py` 第 1301-1304 行

## [x] Task 6: 移除默认管理员凭据（问题 6）
- **Priority**: P1
- **Depends On**: None
- **Description**: 
  - 移除 `db.py` 中开发模式自动创建 `admin:admin` 账户的逻辑
  - 通过环境变量 `MCMONITOR_ADMIN_USERNAME` 和 `MCMONITOR_ADMIN_PASSWORD` 配置初始管理员
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-6.1: 首次启动数据库为空时，不自动创建 `admin` 用户
  - `programmatic` TR-6.2: 设置环境变量后，自动创建指定的管理员账户
- **Notes**: 修改 `db.py` 第 345-358 行

## [x] Task 7: Docker 非 root 用户运行（问题 8）
- **Priority**: P1
- **Depends On**: None
- **Description**: 
  - 在 Dockerfile 中创建非 root 用户 `mcmonitor`
  - 使用 `USER` 指令切换至非特权用户运行
  - 设置正确的文件权限
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `programmatic` TR-7.1: 容器内运行用户为 `mcmonitor`，而非 `root`
- **Notes**: 修改 `Dockerfile`