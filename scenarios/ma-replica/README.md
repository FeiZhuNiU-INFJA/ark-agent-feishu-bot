# 场景2：MA 复刻客户 Agent

> 把**客户自研 Agent 的运行轨迹**在火山方舟 Managed Agents（MA）上**复刻**出来，用**同样的
> user message** 重跑 Session，再和原轨迹对比**端到端耗时 / token 消耗 / cache 命中率**，
> 用来评估「迁移到 MA 是否更优」。

客户给若干条自研 Agent 轨迹（含 system prompt、skill、工具调用）→ 离线拆成中间产物 →
在 MA 上还原 skill + mock 工具返回 + 实跑 Session → 出一份对比报告。

## 本场景的产物

| 产物 | 定位 | 目录 |
| --- | --- | --- |
| **ma-replica-builder** | 复刻方法论 + 两层冻结的可复用件（这是本场景的核心，一切从这里开始） | [skills/ma-replica-builder/](skills/ma-replica-builder/) |

> 场景1 是「跑一个常驻服务」；场景2 是「做一次可复现的迁移评估实验」——它不是常驻程序，而是一套
> 拿到客户轨迹后按流程走一遍、产出对比报告的**工作流**。所以本场景的主体是一个 skill，而非一个 CLI。

## 复刻流程（一图）

```text
客户自研 Agent 轨迹（*.json）
        │  ① extract：认这个客户的轨迹结构，拆成中间产物契约
        ▼
  中间产物（replay_map / skill_bodies / system_prompt / queries …）
        │  ② build_skill_bundle：还原成 Claude Skills SKILL.md 树
        │  ③ gen_file_mocks：把每次工具调用物化成文件（变体 B）
        ▼
   两种 mock 模式在 MA 上实跑同样的 user message
        ├── files ：静态文件 mock，模型用内置 read 读
        └── custom：注册 custom tool，客户端严格回放录制数据
        │  ④ ma_runtime：建 agent/env/session、跑事件循环、采指标
        ▼
   ⑤ report：MA 侧 vs 自研侧对比报告（耗时/token/cache/失败率）
```

**两层冻结**是本场景的设计核心：`①` 与 mock 模式里「客户特有的工具语义」随客户变（照
`example-demo/` 现写）；`②③④⑤` 只吃中间产物契约、跨客户复用不改。详见
[skills/ma-replica-builder/references/00-frozen-vs-client.md](skills/ma-replica-builder/references/00-frozen-vs-client.md)。

## 目录结构

```text
scenarios/ma-replica/
├── README.md                 # 本文件：场景导览
├── skills/
│   └── ma-replica-builder/   # 复刻构建器（方法论 + 冻结层脚本 + 参照样板）
│       ├── SKILL.md          # ★ 完整流程与命令，上手从这里读
│       ├── PROBLEMS.md       # 踩坑与口径边界（换客户前先读）
│       ├── scripts/          # 冻结层：ark_min / ma_runtime / report / build_skill_bundle / gen_file_mocks / case_paths
│       ├── references/       # 分步参考（00~07）
│       └── example-demo/     # 合成参照样板（Acme 客服工单分诊）：extract/run + 轨迹 + data 基准
├── ma-cases/                 # ★ per-case 运行期数据（原始轨迹/抽取产物/实跑/报告），不入库（.gitignore）
│   └── <case>/               # 一个 case = 一次「拿某客户某批轨迹做复刻实验」
└── context/                  # 场景相关的客户原始材料，不入库（.gitignore）
```

- **skill 自带样板 vs per-case 数据分离**：`example-demo/` 是入库的合成参照（可复现基准）；真实客户
  轨迹与实跑产物一律落在 `ma-cases/<case>/`，属运行期数据、**不入库**。
- **一个 case 一个目录**：`ma-cases/<case>/` 下 `trajectories/`（原始轨迹）、`shared/`（抽取产物，
  两模式共享）、`files-mode/` `custom-mode/`（分模式实跑）、`reports/`（对比报告）。布局由冻结层
  [skills/ma-replica-builder/scripts/case_paths.py](skills/ma-replica-builder/scripts/case_paths.py) 钉死。

## 快速开始

准备：Python 3.11 + `httpx`（本场景脚本的**唯一**第三方依赖），live 实跑再加火山方舟 `ARK_API_KEY`
（只做离线抽取/建 mock 可不给）。本场景**不依赖**场景1 的 `arkagent` 包与根 `environment.yml`／`pyproject.toml`
（那套 conda env `customer-a-ma-demo` 及其 `lark-oapi`/`mcp`/`uvicorn` 依赖是场景1 专用的），自建一个最小环境即可：

```bash
python3.11 -m venv .venv && source .venv/bin/activate   # 或 conda create -n ma-replica python=3.11
pip install httpx
```

```bash
# cwd = skill 根
cd scenarios/ma-replica/skills/ma-replica-builder

# ① 离线：抽取中间产物 → 还原 skill → 物化文件 mock（把客户轨迹放进 ../../ma-cases/<case>/trajectories/）
python example-demo/scripts/extract_trajectories.py --case-dir ../../ma-cases/<case>
python scripts/build_skill_bundle.py               --case-dir ../../ma-cases/<case>
python scripts/gen_file_mocks.py                   --case-dir ../../ma-cases/<case>

# ② live 实跑 + 对比报告（正式交付口径：两模式 + 全部轨迹 + 每条并发重复 5 次取均值）
export ARK_API_KEY=...
python example-demo/scripts/run.py --case-dir ../../ma-cases/<case> --mock both --all --repeats 5
```

先拿 skill 自带的合成样板跑通再换真实客户：把 `--case-dir` 换成
`example-demo`（`extract` 用 `example-demo/scripts/extract_trajectories.py --traj-dir example-demo/trajectories --out-dir example-demo/data` 复现基准）。

> 完整流程、命令细节、执行纪律（live 是长任务，要盯到报告出来才停）与口径边界，见
> [skills/ma-replica-builder/SKILL.md](skills/ma-replica-builder/SKILL.md) 与
> [skills/ma-replica-builder/PROBLEMS.md](skills/ma-replica-builder/PROBLEMS.md)。

## 参考资料

- 本场景 skill：[skills/ma-replica-builder/SKILL.md](skills/ma-replica-builder/SKILL.md)
- MA 官方文档合集（跨场景通用）：[common/docs/火山方舟_ManagedAgents_docs.md](../../common/docs/火山方舟_ManagedAgents_docs.md)
- [火山方舟：Managed Agents API](https://docs.volcengine.com/docs/82379/2555910?lang=zh)（复刻实验用到的 create agent/environment/session、事件流等一手文档）
- 仓库最佳实践索引：[根 README](../../README.md)
