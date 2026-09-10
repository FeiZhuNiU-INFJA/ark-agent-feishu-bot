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
| **MA 复刻客户 Agent** | 把客户自研 Agent 的运行轨迹在 MA 上复刻重跑，对比耗时/token/cache，评估「迁移到 MA 是否更优」。 | [scenarios/ma-replica/skills/ma-replica-builder/](scenarios/ma-replica/skills/ma-replica-builder/) |

## 通用件（common/）

- **MA 官方文档合集**：[common/docs/火山方舟_ManagedAgents_docs.md](common/docs/火山方舟_ManagedAgents_docs.md) —— 从火山方舟文档中心抓取拼接的 Managed Agents 全量文档，两个场景都引用它作为权威出处。
- **volc-docs-sync skill**：[common/skills/volc-docs-sync/](common/skills/volc-docs-sync/) —— 按 DocumentID 区间幂等同步上面这份合集。用法：

  ```bash
  python3 common/skills/volc-docs-sync/update_docs.py            # 更新合集
  python3 common/skills/volc-docs-sync/update_docs.py --dry-run  # 只诊断不写文件
  ```

## 快速开始

打包配置留在**仓库根**，`pip install -e .` 通过 `package-dir` 把包目录指到 `scenarios/feishu-bot/`（import 名仍是 `arkagent` / `mock_mcp`）：

```bash
conda env create -f environment.yml
conda activate customer-a-ma-demo
pip install -e ".[dev]"     # 安装 arkagent / customer-a-mock-mcp 命令
pytest -q                   # 全量单测（指向 scenarios/feishu-bot/tests）
```

场景1 的完整起步（扫码建飞书应用、`arkagent init/run`、配置项、模块速查）见 [scenarios/feishu-bot/README.md](scenarios/feishu-bot/README.md)。
场景2 的复刻流程（轨迹抽取、mock、MA 实跑、对比报告）见 [scenarios/ma-replica/skills/ma-replica-builder/SKILL.md](scenarios/ma-replica/skills/ma-replica-builder/SKILL.md)。

## 参考资料

- [火山方舟：Managed Agents API](https://docs.volcengine.com/docs/82379/2555910?lang=zh)
- [飞书：一键创建飞书智能体应用](https://open.feishu.cn/document/mcp_open_tools/integrating-agents-with-feishu/overview)
