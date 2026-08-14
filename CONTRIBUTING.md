# 贡献指南

感谢你对 AgentHub 的关注和贡献！本指南会帮助你了解如何提 Issue 和提交 PR。

## 如何提 Issue

在提交 Issue 前，请先搜索是否已存在相同问题。

一个清晰的 Issue 应包含：

- 环境信息：操作系统、Python/Node 版本、数据库版本
- 复现步骤：越具体越好
- 期望行为与实际行为
- 相关日志或报错信息（注意不要贴出 API Key 等敏感信息）
- 适用的标签（如 `bug`、`enhancement`、`documentation`）

## 如何提交 Pull Request

1. Fork 本仓库并克隆到本地
2. 基于 `main` 创建功能分支：
   ```bash
   git checkout -b feat/my-feature
   ```
3. 完成修改，并补充必要的测试与文档
4. 运行本地检查：
   ```bash
   # 后端
   cd backend
   black .
   ruff check .
   pytest

   # 前端
   cd frontend
   npm run lint
   npm run format:check
   npm run test:run
   ```
5. 提交并推送分支，然后发起 Pull Request

## 代码规范

- Backend：使用 [Black](https://github.com/psf/black) 格式化、[Ruff](https://github.com/astral-sh/ruff) 做 lint
- Frontend：使用 ESLint + Prettier
- 测试：Backend 用 pytest，Frontend 用 Vitest
- 新功能应包含对应测试，合并前保证全部通过

## Commit 规范

建议使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```text
feat: 新增多智能体编排
fix: 修复枚举值大小写问题
docs: 更新 README
chore: 更新依赖
```

## 许可

贡献即表示你同意将代码以 MIT 许可协议发布。
