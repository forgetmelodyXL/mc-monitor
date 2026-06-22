# MC-Monitor 安全审计修复 - 产品需求文档

## Overview
- **Summary**: 修复 MC-Monitor 应用中的 5 个安全漏洞（3 Critical + 1 High + 1 Medium），包括硬编码密钥、API 路径注入、密码重置漏洞、CSRF 绕过和开放重定向。
- **Purpose**: 消除安全审计报告中发现的严重安全风险，确保应用在生产环境中的安全性。
- **Target Users**: 所有使用 MC-Monitor 的用户和管理员

## Goals
- 修复所有 Critical 级别的安全漏洞
- 修复 High 和 Medium 级别的安全漏洞
- 消除攻击链，防止会话伪造和特权提升
- 确保 API 端点的输入验证和 CSRF 防护

## Non-Goals (Out of Scope)
- 不添加新功能或业务逻辑
- 不进行性能优化
- 不修改用户界面设计
- 不处理 Low 和 Info 级别的问题（CDN SRI、限流器线程安全）

## Background & Context
基于 Strix 安全审计平台的白盒审计报告（编号 STRIX-2026-0622-001），发现 MC-Monitor 存在多处严重安全漏洞，攻击者可通过这些漏洞实现会话伪造、特权提升和系统完全控制。

## Functional Requirements
- **FR-1**: 移除硬编码的默认 SECRET_KEY，生产环境未配置时拒绝启动
- **FR-2**: 对 Minekuai `instance_id` 参数实施严格的正则白名单校验
- **FR-3**: 管理员密码重置需验证管理员当前密码
- **FR-4**: 为所有 API 和 Minekuai 路由添加 CSRF 防护
- **FR-5**: 修复登录 `next` 参数的开放重定向漏洞
- **FR-6**: 移除默认管理员凭据的自动创建
- **FR-7**: Docker 容器以非 root 用户运行

## Non-Functional Requirements
- **NFR-1**: 修复后的应用应保持原有功能正常运行
- **NFR-2**: CSRF 防护不应影响现有 AJAX 请求流程
- **NFR-3**: 所有输入验证应返回清晰的错误信息

## Constraints
- **Technical**: 必须使用现有 Flask 框架，不引入新依赖
- **Business**: 修复应尽快完成，优先处理 Critical 级别漏洞
- **Dependencies**: 无外部依赖变更

## Assumptions
- 用户已了解安全风险并同意进行修复
- 修复不会导致现有用户数据丢失
- 应用部署环境支持设置环境变量

## Acceptance Criteria

### AC-1: SECRET_KEY 硬编码修复
- **Given**: 环境变量 `MCMONITOR_SECRET_KEY` 未设置
- **When**: 应用在生产模式下启动
- **Then**: 应用拒绝启动并抛出错误
- **Verification**: `programmatic`

### AC-2: instance_id 路径注入防护
- **Given**: 用户提交包含路径遍历字符的 `instance_id`
- **When**: 绑定实例或调用 Minekuai API
- **Then**: 服务器返回 400 错误，拒绝请求
- **Verification**: `programmatic`

### AC-3: 管理员密码重置验证
- **Given**: 管理员尝试重置用户密码
- **When**: 未提供管理员当前密码
- **Then**: 操作被拒绝，提示需要验证当前密码
- **Verification**: `human-judgment`

### AC-4: API CSRF 防护
- **Given**: 恶意网站发起跨站 POST 请求到 `/api/` 或 `/minekuai/` 路由
- **When**: 请求不包含有效 CSRF 令牌
- **Then**: 服务器返回 403 错误
- **Verification**: `programmatic`

### AC-5: 开放重定向修复
- **Given**: 用户访问 `login?next=//evil.com`
- **When**: 登录成功后
- **Then**: 用户被重定向到默认页面，而非外部网站
- **Verification**: `programmatic`

### AC-6: 默认管理员凭据移除
- **Given**: 应用首次启动（开发模式）
- **When**: 数据库为空
- **Then**: 不自动创建 `admin:admin` 账户
- **Verification**: `programmatic`

### AC-7: Docker 非 root 运行
- **Given**: Docker 容器启动
- **When**: 检查运行用户
- **Then**: 容器以非 root 用户运行
- **Verification**: `programmatic`

## Open Questions
- [ ] 是否需要为现有部署提供迁移指南（如生成新密钥）
- [ ] 是否需要添加密码复杂度要求