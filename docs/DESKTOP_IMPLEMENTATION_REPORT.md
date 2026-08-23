# Synplex AgentHub 桌面客户端实施报告

> 日期：2026-08-23 | 最终提交：38bb64f | 状态：已交付

## 一、需求与方案

目标：在不复制后端、不要求用户本机启动 Docker 的前提下，为 AgentHub 提供可安装的 macOS GUI 客户端。

选择 Tauri v2：复用现有 React/Vite 前端，桌面包仅 13MB；客户端通过 HTTPS 连接 `https://synplex.xyz/api`。相比 Electron，Tauri 包体更小、内存更低、Rust 原生壳可控。

交付功能：原生窗口（1280×820）、应用图标、菜单栏托盘、DMG 安装包、桌面 API 基址、HashRouter、外链系统浏览器、Tauri CORS、桌面 CI 构建。

## 二、执行过程与所有问题（透明记录）

### 1. Rust/Cargo 未安装
- 现象：`rustc: command not found`、`cargo: command not found`。
- 原因：Tauri 原生壳必须使用 Rust 编译；Node/Xcode 工具已有。
- 修复：通过 rustup 安装 Rust 1.98.0 / Cargo 1.98.0，并确认新终端自动加载 `~/.cargo/env`。
- 结果：`cargo check`、release 构建通过。

### 2. ESLint 扫描 Tauri 生成目录
- 现象：lint 报 `src-tauri/target/**/__global-api-script.js` 与二进制 JS 错误。
- 原因：ESLint 默认扫描 Rust target/generated/vendor 第三方文件。
- 修复：eslint.config.js 忽略 `src-tauri/target`、`gen`、`vendor`。
- 结果：lint 0 error（保留 4 个历史 Fast Refresh warning）。

### 3. 后端测试连接本地数据库失败
- 现象：feedback 测试连接 localhost:5433 失败。
- 原因：用户已关闭 Docker Desktop，本机 PostgreSQL 容器不运行；不是桌面客户端代码问题。
- 处理：只运行不依赖本地数据库的 config/security/probe 测试；完整后端由 GitHub CI 的真实 PostgreSQL/Redis/MailHog 服务验证。

### 4. DMG 打包偶发失败
- 现象：Tauri `bundle_dmg.sh` 失败，并残留 `/Volumes/dmg.*` 挂载。
- 原因：macOS create-dmg/Finder 布局脚本偶发未卸载临时读写镜像。
- 修复：卸载残留卷；使用稳定手动流程（签名 .app → hdiutil UDZO）重建 DMG。
- 结果：DMG 可挂载，内部 App 签名验证通过。

### 5. App 资源签名不完整
- 现象：`codesign --verify --deep --strict` 提示 resources 未密封。
- 原因：无 Apple Developer ID 时 Tauri 只生成 linker ad-hoc 签名，未密封 Bundle Resources。
- 修复：构建后执行 `codesign --force --deep --sign -`，再重建 DMG。
- 结果：/Applications 与 DMG 内 App 均通过严格签名校验。

### 6. 生产 CORS 首次仍返回 400
- 现象：`Origin: tauri://localhost` 预检 400。
- 原因：修改 `.env` 后只 restart 容器，Docker 不会重新注入环境变量。
- 修复：`docker compose up -d --force-recreate backend`。
- 结果：三个来源均返回 200 + 对应 allow-origin：tauri://localhost、http://tauri.localhost、https://tauri.localhost。

### 7. 生产构建导致服务器暂时无响应
- 现象：部署命令超时，SSH banner 与 HTTPS 暂时不响应，load average 最高超过 160。
- 原因：4C/4G 服务器无 swap，同时并行构建 backend/frontend，触发资源饥饿；服务未宕机，构建完成后恢复。
- 修复：等待构建完成；增加 2GB swap；production-deploy.sh 固定 `COMPOSE_PARALLEL_LIMIT=1` 串行构建。
- 结果：后续部署稳定，生产 health 全绿。

### 8. 项目一/项目二共用 Git 仓库导致分支污染
- 现象：原工作区 remote 指向 factory-rca-agent，Tauri 提交落在 v0.3-dev 分支；生产一度含项目二历史。
- 原因：另一个并发任务正在同目录开发项目二，改变了 branch/remote。
- 修复：创建干净独立工作区 `/Users/weijiakang/agenthub-project1`，以项目一最后稳定提交 6f47894 为基点，只 cherry-pick Tauri 提交；force-with-lease 恢复 AgentHub GitHub main；生产 reset 到干净历史；保留项目二分支不动。
- 结果：项目一本地/GitHub/生产均为干净 AgentHub 历史；项目二继续使用原工作区，互不覆盖。

### 9. 摄像头/iPhone Continuity Camera 提示
- 现象：启动 Tauri App 后 macOS/iPhone 显示摄像头相关提示；TCC 日志出现 camera/microphone preflight。
- 审计：源码无 getUserMedia/mediaDevices 调用；Info.plist 无 Camera/Microphone UsageDescription；TCC 结果 `authValue=1, preflight=yes`，表示权限未决定、未授权，不是拍摄/录音。
- 根因：macOS WKWebView 初始化会预检媒体权限；上游 WRY 的 WKUIDelegate 默认实现还会 Grant 媒体请求。
- 修复：
  1. 桌面 HTML 启动前注入 media API 拒绝脚本；
  2. CSP 增加 `media-src 'none'`；
  3. vendored WRY 移除 `requestMediaCapturePermission` selector，杜绝上游自动 Grant；
  4. 关闭主窗口改为完全退出，不再隐藏到托盘。
- 说明：WKWebView 启动仍会做 TCC preflight 查询（系统行为，无法由页面阻止），但没有权限、没有摄像头调用、没有录制。用户可直接关闭 iPhone 摄像头提示；退出 App 后进程完全消失。

### 10. 用户模型一直报错
- 用户配置：Base URL `http://158.94.173.197:8080/v1`，Key 有效。
- 直接验证：`/models` 200，返回 gpt-5.4、gpt-5.5、gpt-5.6-luna/sol/terra、gpt-image-2。
- 根因：gpt-5.4 虽在模型列表，但 `/chat/completions` 返回 502 Upstream request failed；不是 Base URL/Key 错误。gpt-5.5 与 5.6-luna/sol/terra 均返回 200。
- 产品修复：新增用户端 `discover-models` 与 `test-connection`；前端自动发现真实模型、排除图片模型、优先推荐 `-sol`；模型测试成功后才允许保存。gpt-5.4 会显示友好错误而非模糊报错。
- 真实用户验证：创建临时普通用户 → 登录 → 发现模型 → gpt-5.4 友好失败 → gpt-5.6-sol 测试成功 → 加密保存 → Chat 模式回复“用户模型接入成功” → Execution `model_used=['gpt-5.6-sol']`、status=completed。测试数据已清理。

## 三、交付物

- `/Applications/Synplex AgentHub.app`（已安装，关闭窗口完全退出）
- `~/Desktop/Synplex AgentHub 桌面版/Synplex AgentHub.app`
- `~/Desktop/Synplex AgentHub 桌面版/Synplex AgentHub_1.0.0_aarch64.dmg`
- 源码：`frontend/src-tauri/`
- 开发文档：`docs/DESKTOP_CLIENT.md`

## 四、最终验证

- macOS ARM64 .app 构建成功，严格 codesign 验证通过；DMG 可挂载且内部 App 验签通过。
- 前端 typecheck、lint、vitest 22/22、Web build、Desktop build 全通过。
- Playwright 8/8（新增“普通用户发现/测试/保存模型”GUI 流程）。
- 后端模型探测/连接/轮换/security 测试 11 passed / 1 skipped。
- GitHub Desktop Client CI 与主 CI 全绿。
- 生产 health：database/redis/llm 均为 true；Tauri 三个 Origin 的 CORS 预检均 200。
- 报告前验证基线：38bb64f；最终版本以 AgentHub main 最新提交为准。

## 五、还需要用户提供什么

当前无需提供任何信息即可使用。

可选项：
1. 用户提供的模型 Key 已出现在对话中，建议测试后轮换；可用模型推荐 gpt-5.6-sol（gpt-5.5/luna/terra 也可），不要选当前上游故障的 gpt-5.4。
2. 若要对外分发并消除 macOS“无法验证开发者”提示，需要 Apple Developer ID（付费账号）用于签名/notarization；本机使用不需要。
