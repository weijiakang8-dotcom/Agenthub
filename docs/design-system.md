# AgentHub Design System

方向：Premium / Minimal / Calm / Precise。默认高级浅色 SaaS，深色 token 已备好，给 `html` 加 `dark` 类即可切换。

## Color

- 主色：`--primary`
- 背景 / 卡片 / 浮层：`--background`、`--card`、`--popover`
- 文字：`--foreground`、`--muted-foreground`
- 边框 / 输入框 / focus ring：`--border`、`--input`、`--ring`
- 语义状态：`--success`、`--warning`、`--danger`、`--info`
- Agent 状态：`--agent-thinking`、`--agent-running`、`--agent-completed`、`--agent-waiting`、`--agent-failed`

## Typography

| Class | Size / Line-height / Weight |
|-------|-----------------------------|
| `.type-display` | 36 / 1.15 / 600 |
| `.type-h1` | 30 / 1.2 / 600 |
| `.type-h2` | 24 / 1.25 / 600 |
| `.type-h3` | 18 / 1.3 / 600 |
| `.type-body` | 15 / 1.55 / 400 |
| `.type-small` | 13 / 1.5 / 400 |
| `.type-caption` | 12 / 1.4 / 400 |
| `.type-label` | 13 / 1.4 / 500 |

## Spacing

统一使用 8px 步进：8 / 12 / 16 / 24 / 32 / 48 / 64。禁止任意 `p-[17px]` 这类魔数。

## Radius

- `rounded-sm`：4px
- `rounded-md`：8px
- `rounded-lg` / `rounded-xl`：12px

## Shadow

- `shadow-xs`：图标 / 小控件
- `shadow-sm`：卡片默认
- `shadow-md`：hover 悬浮卡片
- `shadow-lg`：弹层 / Dropdown

## Motion

- `100ms`：hover / 颜色 / opacity
- `150ms`：常规过渡
- `200ms`：面板 / 弹层
- `300ms`：页面级或较大位移

所有状态色、阴影、圆角、字体层级都应通过 token 消费，不要在页面中硬编码 hex 或随意取值。
