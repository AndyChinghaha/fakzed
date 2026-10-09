# 贡献指南

感谢你对 fakzed 的关注！本指南帮助你快速上手开发并提交高质量贡献。

## 项目结构

```
libs/fakzed/         # 核心 SDK：Agent / Team / Workflow + 可插拔能力
libs/fakzed-server/  # 平台层：Agent 注册中心 + REST/SSE API + 多租户
apps/ui/             # Web 控制台（Next.js + Tailwind）
docs/                # 文档
cookbook/            # 可运行示例（含 CI 校验）
```

## 环境准备

```bash
# 1. 安装 uv（Python 包管理与构建）
# 2. 同步开发环境
uv sync

# 3. Web UI（可选，需 Node 20+）
cd apps/ui && npm install
```

## 开发工作流

```bash
# 代码质量（提交前必须全部通过）
uv run ruff check .
uv run ruff format --check .
uv run mypy libs/fakzed/src libs/fakzed-server/src

# 测试
uv run pytest

# 运行单个示例
uv run python cookbook/01_hello_agent.py
```

## 代码规范

- **Python 3.10+**，类型标注完整（mypy 零错误）
- 代码风格由 **ruff** 统一（先 `ruff format .` 再提交）
- 新功能必须配套测试（目标覆盖率 ≥ 85%）
- docstring 使用英文，注释可用中文或英文

## 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
feat: 新功能
fix: 修复
docs: 文档
test: 测试
refactor: 重构
chore: 杂项
```

## Pull Request 流程

1. Fork 本仓库并创建功能分支
2. 开发 + 测试 + 通过全部质量检查
3. 提交 PR，描述清楚变更动机与影响范围
4. CI 自动运行 lint / type-check / 测试 / UI 构建
5. 维护者审查通过后合并

不确定改什么？看看 [Issues](../../issues) 里带 `good first issue` 标签的任务，或者直接开 Issue 讨论你的想法。
