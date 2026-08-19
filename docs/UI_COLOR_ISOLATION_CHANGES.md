# AgentHub 前端配色隔离调整 — 改动清单

> 需求范围：修复登录 / 注册弹窗文字与背景融合、可读性差的问题；全站点其余弹窗 / 二级页面统一做浮层视觉隔离与对比度校验。
> 硬性约束：首页（`src/pages/Landing.tsx`）与工作台主页（`src/pages/Dashboard.tsx`）的样式、布局、配色完全未改动。

## 根因

- 全局通过 `main.tsx` 的 `.dark` 包装实现深色主题，但 Radix 弹窗 / 下拉 / Toast 等浮层通过 Portal 渲染到 `body`，脱离 `.dark` 作用域，颜色来源不确定；
- 登录 / 注册弹窗此前叠加了深色渐变背景，而文字仍按浅色主题的深色前景渲染，形成“深色背景 + 黑色文字”的融合缺陷。

## 统一方案

新增 `surface-isolated` 隔离表面（`frontend/src/index.css`）：

- 独立白底 `#FFFFFF`，不继承底层页面背景；
- 主文本 `#1F2937`，辅助 / 占位文字 `#6B7280`（白底对比度 4.83:1，满足 WCAG 2.1 AA）；
- 主按钮 `#4F46E5` + 白字（对比度 6.29:1）；
- 圆角 + 阴影：弹窗 `rounded-lg`（12px）+ `shadow-xl`，下拉 / 菜单 / Toast `rounded-md` + `shadow-md`；
- 遮罩统一为半透明黑 `rgba(0, 0, 0, 0.45)`；
- 保留原有 fade / zoom / slide 过渡动画。

## 修改文件与内容

| 文件 | 调整内容 |
| --- | --- |
| `frontend/src/components/AuthModal.tsx` | 登录 / 注册 / 找回密码弹窗：移除深色渐变底，改为白底 + `#1F2937` 文字 + `#6B7280` 辅助文字 + 阴影；保留原有品牌 Logo 与标题结构 |
| `frontend/src/components/ui/dialog.tsx` | `DialogContent` 全局应用白底隔离表面；遮罩 `bg-black/50` → `bg-black/45`；阴影升级 |
| `frontend/src/components/ui/sheet.tsx` | 移动端导航抽屉应用白底隔离表面；遮罩统一 45% 黑；阴影升级 |
| `frontend/src/components/ui/select.tsx` | Select 下拉面板应用白底隔离表面 + 深色文字 |
| `frontend/src/components/ui/dropdown-menu.tsx` | 用户菜单等下拉菜单应用白底隔离表面 + 深色文字 |
| `frontend/src/components/ui/tooltip.tsx` | Tooltip 改为白底深字，箭头同步白色 |
| `frontend/src/components/ui/sonner.tsx` | 消息提示 Toast 白底 + `#1F2937` 文字 + 浅灰边框 |
| `frontend/src/index.css` | 新增 `.surface-isolated` 隔离表面设计令牌 |

## 覆盖范围（需求清单逐项）

- 登录弹窗 ✅
- 注册弹窗 ✅
- 找回密码弹窗 ✅（AuthModal `forgot` 流程）
- 表单弹窗 / 新建执行弹窗（`CreateExecutionDialog`）✅
- 消息提示弹窗（Toast）✅
- 二次确认弹窗：代码库中不存在独立二次确认弹窗组件，删除类操作当前为直接执行，无遗漏对象 ✅
- 设置页面 / 密钥管理 / 知识库 / 模型 / 通知 / 用量 / 评测（Settings 各面板）✅ 页面级对比度校验通过
- Skill 库 / 工作流 / 工作流编辑器 / 执行记录 / 执行详情（日志）/ 质量看板 / 告警中心 / 告警规则 / 对话 / 历史 / 使用指南 ✅ 页面级对比度校验通过
- 个人资料页：当前版本无独立个人资料页（Header 中“个人设置”为占位菜单项），无需调整
- Agent 创建 / 编辑页：当前版本对应 Skill 库创建与工作流编辑器，已覆盖 ✅

## 禁止修改清单核验

- `frontend/src/pages/Landing.tsx`：未修改（工作区中已有来自其他任务的未提交改动，本次未触碰）
- `frontend/src/pages/Dashboard.tsx`：未修改
- 未反向改动首页 / 工作台原有色彩方案

## 渲染验收结果（Playwright + Chromium 实测）

### 弹窗 / 浮层

| 元素 | 背景 | 文字 | 对比度 | 结果 |
| --- | --- | --- | --- | --- |
| 登录弹窗 | 白 #FFFFFF | 标题 #1F2937 | 14.68:1 | ✅ |
| 登录弹窗表单 / 占位符 | 白 | #1F2937 / #6B7280 | ≥4.83:1 | ✅ |
| 注册弹窗 | 白 | #1F2937 | 14.68:1 | ✅ |
| 找回密码弹窗 | 白 | #1F2937 | 14.68:1 | ✅ |
| 新建执行弹窗 | 白 | 主文字 / 辅助 4.83:1 | ≥4.83:1 | ✅ |
| Select 下拉 | 白 | #1F2937 | 13.13:1 | ✅ |
| 新手引导弹窗 | 白 | 主文字 / 辅助 4.83:1 | ≥4.83:1 | ✅ |
| 用户菜单 | 白 | #1F2937 | 14.68:1 | ✅ |
| 消息提示 Toast | 白 | #1F2937 | 14.68:1 | ✅ |
| 移动端导航抽屉 | 白 | 菜单项 4.83:1 | ≥4.83:1 | ✅ |
| 弹窗遮罩 | rgba(0,0,0,0.45) | — | — | ✅ |

### 二级页面（页面本身保持深色主题不变）

标题 / 正文 / 次要文字与页面背景对比度均在 7.0:1 以上（例如工作台主页 17.12:1、对话历史 17.12:1、工作流编辑器 7.05:1），全部满足 WCAG 2.1 AA。

## 质量检查

- `npm run typecheck`：通过
- `npm run lint`：通过（仅 3 条既有 warning，与本次改动无关）
- `npm run test:run`：18/18 通过
- `npm run format:check`：本次修改文件全部符合 Prettier；仓库中另有 5 个既有文件格式告警，属历史遗留，未纳入本次改动
