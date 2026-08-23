# Synplex AgentHub 桌面客户端

> 技术方案：Tauri v2 + 现有 React/Vite 前端。桌面客户端连接 `https://synplex.xyz/api`，不内置后端、不要求 Docker。

## 功能

- 完整复用 Web 端：登录/注册、聊天三模式、调度中心、Skill、Agent、执行记录、省钱账单、用户反馈；
- 原生 macOS 窗口（1280×820，最小 960×640）；
- 菜单栏托盘：打开 AgentHub / 退出；关闭主窗口时隐藏到托盘，任务不中断；
- 独立应用图标与 DMG 安装包；
- 桌面构建通过 `VITE_API_BASE_URL=https://synplex.xyz/api` 连接生产 API，Web 构建仍使用相对 `/api`；
- 后端 CORS 已允许 `tauri://localhost` / `http(s)://tauri.localhost`。

## 开发

前置：Node.js 20+、Rust stable、Xcode Command Line Tools。

```bash
cd frontend
npm install
npm run desktop:dev
```

`desktop:dev` 会启动 Vite（127.0.0.1:5173）并打开 Tauri 窗口。开发模式仍由 Vite 代理 `/api` 到本机 8000 后端。

## 构建 macOS 安装包

```bash
cd frontend
npm run desktop:build
```

产物：

```text
frontend/src-tauri/target/release/bundle/macos/Synplex AgentHub.app
frontend/src-tauri/target/release/bundle/dmg/Synplex AgentHub_1.0.0_aarch64.dmg
```

## 安装与 Gatekeeper

当前为未签名的个人构建，首次打开 macOS 可能提示"无法验证开发者"：

1. 右键应用 → 打开 → 确认；或
2. 系统设置 → 隐私与安全性 → 仍要打开。

正式外部分发需要 Apple Developer ID 签名与 notarization（需付费开发者账号），这不影响本机/面试演示。

## 安全与数据

- JWT 保存在 Tauri WebView 的本地存储空间（与浏览器 localStorage 语义一致，应用间隔离）；
- API Key 仍由后端加密保存，桌面包内不包含任何密钥；
- 所有业务数据在生产服务器，卸载桌面客户端不会删除账号或执行记录。

## 配置

桌面专用环境：`frontend/.env.desktop`

```env
VITE_API_BASE_URL=https://synplex.xyz/api
VITE_DESKTOP_CLIENT=true
```

如需连接测试环境，复制为新的 Vite mode（例如 `.env.staging-desktop`）并修改 API 地址。
