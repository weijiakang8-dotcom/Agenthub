# Synplex AgentHub 桌面客户端

> 技术方案：Tauri v2 + 现有 React/Vite 前端。桌面客户端连接 `https://synplex.xyz/api`，不内置后端、不要求 Docker。

## 功能

- 完整复用 Web 端：登录/注册、聊天三模式、调度中心、Skill、Agent、执行记录、省钱账单、用户反馈；
- 原生 macOS 窗口（1280×820，最小 960×640）；
- 菜单栏托盘：打开 AgentHub / 退出；**关闭主窗口即完全退出**（不隐藏驻留，避免隐蔽资源占用）；
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

本机推荐使用根目录安装脚本。它会从当前源码重新构建、ad-hoc 重签名、备份现有应用、刷新 LaunchServices 并安装到 `/Applications`：

```bash
bash scripts/install-macos-desktop.sh
```

产物：

```text
frontend/src-tauri/target/release/bundle/macos/Synplex AgentHub.app
frontend/src-tauri/target/release/bundle/dmg/Synplex AgentHub_1.0.0_aarch64.dmg
```

## 安装与 Gatekeeper

当前本机构建使用 ad-hoc 签名，不具备 Apple Developer ID 和 notarization。安装脚本会校验包完整性、移除本机构建的 quarantine 标记并刷新 LaunchServices。若手工复制 DMG 中的应用，首次打开仍可能提示"无法验证开发者"：

1. 右键应用 → 打开 → 确认；或
2. 系统设置 → 隐私与安全性 → 仍要打开。

正式外部分发必须使用 Apple Developer ID 签名与 notarization（需要付费开发者账号）。ad-hoc 包只适用于受控本机安装。

## 安全与数据

- **项目不使用摄像头/麦克风**：源码无 `getUserMedia`，Info.plist 无 Camera/Microphone 权限；
  桌面包注入媒体 API 拒绝脚本、设置 CSP `media-src 'none'`，并在 vendored WRY 原生层移除
  `requestMediaCapturePermission` selector（上游默认会 Grant）。关闭窗口会完全退出进程；
- macOS 的 WKWebView 启动时仍会向 TCC 做 camera/microphone **preflight（仅查询）**；系统日志中
  `authValue=1 / preflight=yes` 表示权限未决定、未授权，不是录像/录音。若 iPhone 弹出 Continuity
  Camera 提示可直接关闭，AgentHub 不需要它；
- JWT 保存在 Tauri WebView 的本地存储空间（与浏览器 localStorage 语义一致，应用间隔离）；
- API Key 仍由后端加密保存，桌面包内不包含任何密钥；
- 用户接入模型时先从 `/models` 自动发现真实模型 ID，再用选定模型执行一次最小请求测试；
  可填写供应商根域、`/v1`、`/models`、`/chat/completions` 或 `/responses` 地址，服务端会规范为实际 API root；
  OpenAI 官方 API 默认使用 Responses API，其他兼容供应商默认使用 Chat Completions；若兼容服务明确拒绝 Chat 端点，测试会自动尝试 Responses，并保存实际模式；
  非对话模型会从选择列表排除。只有测试成功后才能保存，避免因填错路径、端点或模型导致 Agent 执行报错；
- 模型探测由生产后端发起，Base URL 仅允许解析到公网地址；本机、私网、链路本地及重定向到私网的地址会被拒绝；
- 所有业务数据在生产服务器，卸载桌面客户端不会删除账号或执行记录。

## 配置

桌面专用环境：`frontend/.env.desktop`

```env
VITE_API_BASE_URL=https://synplex.xyz/api
VITE_DESKTOP_CLIENT=true
```

如需连接测试环境，复制为新的 Vite mode（例如 `.env.staging-desktop`）并修改 API 地址。
