# AgentHub 企业级架构

本文档描述 AgentHub 的企业级 SaaS 能力：多租户、RBAC 权限、数据隔离与审计体系。

## 1. 多租户设计

AgentHub 以 `Organization` 为租户边界，每个注册用户都会创建一个独立组织。

核心模型均携带 `organization_id`：

- `users`
- `workflows`
- `executions`
- `documents`
- `model_configs`
- `conversations`
- `tool_calls`
- `audit_logs`

所有业务查询都通过 `CurrentUserDep` 获取当前用户，并以 `current_user.organization_id` 过滤，禁止跨组织访问。

## 2. RBAC 模型

### 角色

| 角色 | 说明 |
|---|---|
| `admin` | 组织管理员，拥有全部权限 |
| `member` | 组织成员，可执行、写资源 |
| `viewer` | 只读成员，仅可查看结果 |

### 权限定义

权限定义在 `backend/app/core/permissions.py`：

| 权限 | 允许角色 |
|---|---|
| `models:manage` | `admin` |
| `members:manage` | `admin` |
| `audit:view` | `admin` |
| `executions:write` | `admin`, `member` |
| `resources:write` | `admin`, `member` |

`admin` 为超级角色，`require_role()` 和 `require_permission()` 都会对 admin 放行。

## 3. 权限流

```text
请求
  ↓
认证中间件 / get_current_user 解析 JWT
  ↓
识别用户与 organization_id
  ↓
路由依赖执行 require_permission()
  ↓
校验 user.role ∈ 权限允许角色
  ↓
通过 → 业务逻辑
拒绝 → 403 { code: FORBIDDEN, message: 没有执行该操作的权限 }
```

## 4. 数据隔离

隔离在两层实现：

1. 列表查询：`SELECT ... WHERE organization_id = current_user.organization_id`
2. 单资源访问：获取资源后校验 `resource.organization_id == current_user.organization_id`，不一致返回 404（避免暴露资源存在性）

组织成员管理接口只能操作当前组织的成员，且禁止修改自己的角色，避免误锁组织管理员。

## 5. 审计体系

`AuditLog` 同时保留 HTTP 请求维度和业务动作维度：

- `method` / `path` / `status_code` / `details`：HTTP 请求审计
- `action` / `resource_type` / `resource_id`：业务动作审计
- `ip_address`：客户端 IP
- `user_id` / `organization_id`：操作主体与租户

审计中间件自动归类常见动作：

- `POST /api/auth/login` → `login`
- `POST /api/auth/register` → `register`
- `POST /api/auth/logout` → `logout`
- `POST /api/executions` → `create_execution`
- `PUT /api/models/{id}` → `update_model`
- `DELETE /api/{resource}/{id}` → `delete_resource`

敏感字段（密码、验证码、API Key、token 等）在写入审计前会被脱敏为 `***`。

管理员可通过 `GET /api/audit-logs` 查看本组织审计日志。

## 6. 相关文件

- `backend/app/core/permissions.py`：RBAC 权限定义
- `backend/app/core/auth_deps.py`：当前用户依赖
- `backend/app/api/deps.py`：认证与依赖兼容出口
- `backend/app/api/routes/organizations.py`：组织成员管理
- `backend/app/models/audit_log.py`：审计模型
- `backend/app/core/audit.py`：审计脱敏与动作分类
- `backend/app/main.py`：审计中间件
