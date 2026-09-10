# Worked example：NIO 6 条销售盘点轨迹

拿现成的 6 条蔚来（NIO）销售「用户深度盘点」轨迹，把 `ma-replica-builder` 的全流程跑通的完整例子。
它既是**回归基准**（脚本改动后重跑，产物应与 `data/` 一致），也是**换客户前的参照样板**。

## 场景

6 条轨迹都是同一类任务：销售顾问针对一个 PPL 用户提问（如"贷款卡住怎么快速下单""在对比问界
M9 怎么沟通""没有购车打算但更新了心愿单怎么跟进"），Agent 拉取该用户的悟空（wukong）业务数据
（销售线索、跟进记录、试驾、企微聊天、心愿单……），套用 `demand-review` 技能的 SOP，产出一份
结构化盘点（状态与需求等级 / 关注点 / 跟进质量 / 成交动力阻力卡点 / 下一步行动 / 沟通话术）。

## 轨迹来源

`docs/context/trajectory/trajectory{1..6}.json`（每个是一次自研 Agent 的完整运行，顶层 `messages[]`）。

## 复现（离线部分，无需 ARK_API_KEY）

```bash
conda activate nio-ma-demo    # 或任意有 httpx 的 py3.11 环境
cd skills/ma-replica-builder

# 准备 case 工作目录：把 6 条原始轨迹放进 <项目>/ma-cases/nio/trajectories/
mkdir -p ../../ma-cases/nio/trajectories
cp ../../docs/context/trajectory/trajectory*.json ../../ma-cases/nio/trajectories/

# 层③ 客户生成式（这个客户现写）：把原始轨迹拆成中间产物契约（读 trajectories/、写 shared/）
python example-nio/scripts/extract_trajectories.py --case-dir ../../ma-cases/nio
# 层② 冻结契约转换器（只吃中间产物，换客户不用改）
python scripts/build_skill_bundle.py  --case-dir ../../ma-cases/nio
python scripts/gen_file_mocks.py      --case-dir ../../ma-cases/nio

# 与 skill 自带的回归基准比对（应无差异；example-nio/data 是入库的参照样本）
diff -rq ../../ma-cases/nio/shared example-nio/data --exclude=ma_runs --exclude=comparison.md
```

> `ma-cases/` 是 per-case 运行期数据（已 gitignore），不入库；固化的参照产物在 `example-nio/data/`，
> 可直接查看，无需重跑。旧口径 `--out-dir <dir>` 平铺目录仍兼容。

## 抽取结果（已验证）

- **api 回放键**：48（工具名 `api_call`），另加 1 个 `current_time` → `replay_map` 共 49 条。
- **skill 正文/子文档**：10 份（加载器 `skill_invoke`），还原成 5 个 SKILL.md：
  - `demand-review`：主文档 + 5 个已披露子文档；**3 个未披露**（`material-bridge.md` /
    `output-examples.md` / `template-examples.md`）已留空标注。
  - `wukong-search`：主文档；**5 个子文档全未披露**（`business_metrics.md` /
    `entity_resolution.md` / `user.md` / `wukong_dsl.md` / `wukong_union_object_query.md`）留空标注。
  - `nio_material_finder` / `nio_pcp_qa` / `nio_sales_assistant`：仅主文档。
- **未披露子文档共 8 个** —— 直接印证"轨迹越多、还原越完整"：补覆盖到这些分支的轨迹再重跑，
  它们会被自动填上。
- **键冲突 2 处**（同键不同返回），抽取端按"取最长成功版"归并。

覆盖矩阵详见 [data/summary.md](data/summary.md)。5 条 query 见 [data/queries.json](data/queries.json)。

## 两套 mock 产物

- **变体 A**（custom tool 动态回放）：用 `data/replay_map.json` + `data/skills/`，由
  `scripts/run.py --mock custom` 在事件循环里严格回放。
- **变体 B**（文件静态 mock）：`data/mocks-skill/` —— 49 条调用物化成
  `mocks/*.txt`（0 条错误返回），台账 `mocks/INDEX.md`，可粘进 system 的
  `data/mock_system_appendix.md`。

## Live 实跑（需 ARK_API_KEY）

离线三步已验证通过；`⑤ 在 MA 实跑 + ⑥ 对比`需要方舟凭据。层③ 客户脚本 `run.py`
（工具面 + 结果路由 + 自研耗时）会调层① 冻结引擎跑完并**自动出对比报告**：

```bash
export ARK_API_KEY=...
cd skills/ma-replica-builder/example-nio/scripts
python run.py --case-dir ../../../../ma-cases/nio --model doubao-seed-2-1-pro-260628 --all   # 默认 files 模式
# 或高保真：python run.py --case-dir ../../../../ma-cases/nio --mock custom --all
# 产出 ma-cases/nio/files-mode/<traj>/run.json（或 custom-mode/）+ ma-cases/nio/reports/comparison-<mode>.md
```

跑过之后把 `bash 抢戏` 观测结论与耗时/token/cache 数字回填到 [../PROBLEMS.md](../PROBLEMS.md)。
