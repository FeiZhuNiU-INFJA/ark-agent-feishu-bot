# 火山方舟 Managed Agents · 最佳实践仓库

> 一组围绕**火山方舟 Managed Agents（MA）**的可运行最佳实践：按**场景**组织，通用件下沉到 `common/`。

每个场景是一个独立目录（含自己的 README、代码、案例）；跨场景共享的东西（MA 官方文档合集及其维护脚本）放在 `common/`。想上手某个场景，直接进它的目录看 README。

## 顶层结构

```text
ark-agent-feishu-bot/
├── README.md            # 本文件：最佳实践索引
├── pyproject.toml       # 打包入口（package-dir 指向 scenarios/feishu-bot）
├── environment.yml      # conda 环境定义
├── common/              # 跨场景通用件
│   ├── docs/            # MA 官方文档合集
│   └── skills/          # 维护上述合集的 skill（volc-docs-sync）
└── scenarios/           # 每个场景一个子目录
    ├── feishu-bot/      # 场景1：MA × 飞书 Bot
    └── ma-replica/      # 场景2：MA 复刻客户 Agent
```

## 场景

| 场景 | 一句话 | 目录 |
| --- | --- | --- |
| **MA × 飞书 Bot** | 把飞书对话机器人接到 MA；含客户A 四卡点（鉴权/透传/岗位/记忆）与群聊共享 Bot 两个案例。 | [scenarios/feishu-bot/](scenarios/feishu-bot/) |
| **MA 复刻客户 Agent** | 把客户自研 Agent 的运行轨迹在 MA 上复刻重跑，对比耗时/token/cache，评估「迁移到 MA 是否更优」。 | [scenarios/ma-replica/](scenarios/ma-replica/) |

## 通用件（common/）

- **MA 官方文档合集**：[common/docs/火山方舟_ManagedAgents_docs.md](common/docs/火山方舟_ManagedAgents_docs.md) —— 从火山方舟文档中心抓取拼接的 Managed Agents 全量文档，两个场景都引用它作为权威出处。
- **volc-docs-sync skill**：[common/skills/volc-docs-sync/](common/skills/volc-docs-sync/) —— 按 DocumentID 区间幂等同步上面这份合集。用法：

  ```bash
  python3 common/skills/volc-docs-sync/update_docs.py            # 更新合集
  python3 common/skills/volc-docs-sync/update_docs.py --dry-run  # 只诊断不写文件
  ```

## 上手

每个场景自带完整的环境搭建与运行说明——进对应目录看 README。跨场景**没有统一的一键安装**：两个场景的依赖与环境相互独立。

- **场景1（MA × 飞书 Bot）**：conda 环境、`pip install -e .`（打包配置在仓库根，`package-dir` 把包目录指到 `scenarios/feishu-bot/`，import 名仍是 `arkagent` / `mock_mcp`，故安装/测试命令**从仓库根执行**）、扫码建应用、`arkagent init/run` —— 见 [scenarios/feishu-bot/README.md](scenarios/feishu-bot/README.md)。
- **场景2（MA 复刻客户 Agent）**：最小环境（仅依赖 `httpx`，不碰场景1 的包）、轨迹抽取 / mock / MA 实跑 / 对比报告 —— 见 [scenarios/ma-replica/README.md](scenarios/ma-replica/README.md)。

> 外部一手文档（火山方舟 / 飞书官网链接）随场景收录在各自 README 的「参考资料」；跨场景权威出处是上面 `common/` 里的 MA 文档合集。
