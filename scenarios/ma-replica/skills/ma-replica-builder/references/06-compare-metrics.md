# 06 · 采集并对比指标（耗时 / token / cache）

## 口径边界（先读，避免误读报告）

| 指标 | 自研侧（原轨迹） | MA 侧（实跑） |
|---|---|---|
| 端到端耗时 | 各步 `_meta.duration` 求和 | wall-clock（发 query 到 idle） |
| input / output token | **不可恢复**（导出只有 messages） | `span.model_request_end.model_usage` 累计 |
| cache 命中 | **不可恢复** | `cache_read / (input_tokens + cache_read)` |

自研轨迹导出通常**只有 `messages`，没有 `usage`**，所以 token/cache **无法从轨迹恢复**，
报告里这两项只给 MA 单边实测。要双边 token 对比，须向客户额外要「全量请求导出」（含 `usage`）。
耗时两侧可比，但注意口径不同（自研=各步 duration 之和，不含排队/网络；MA=真实墙钟）。

## 指标从哪来

- **MA 侧**：冻结层 `ma_runtime.run_query` 已在事件循环里把每个
  `span.model_request_end.model_usage` 收进 `usage_per_request`，并累加成 `usage_total`
  （`input_tokens` / `output_tokens` / `cache_creation_input_tokens` / `cache_read_input_tokens`）。
  Session 级用量靠客户端自己累加——MA 不给现成的 session 汇总。
- **自研侧**：冻结层 `report.build_report` 通过客户传入的 `self_side` 回调拿"自研耗时/步数"。
  轨迹结构客户特异，所以本样例在 `run.py` 的 `make_self_side()` 里实现（读 `_meta.duration` 求和
  + 数 assistant 步数）。

## 生成对比报告

`run.py` 跑完会**自动**调 `report.build_report` 生成 `comparison.md`，无需单独一步。
（要单独重算，在客户样板里 `from report import build_report` 再调一次即可。）

`comparison.md` 结构：

1. **逐条对比表**：每条轨迹一行——自研耗时/步数、MA 耗时/模型请求数/入出 token/cache_read/
   cache 命中率、custom 未命中数、是否 bash 抢戏。
2. **MA 侧汇总**：累计 in/out token、cache_read、cache_creation，整体 cache 命中率。
3. **保真度旁注**：custom 未命中总数（>0 说明模型走出录制轨迹，需补轨迹或收敛 query）、
   是否检测到 bash 抢戏。
4. **口径说明**：重申自研 token 不可恢复、MA cache 命中依赖多轮 prefix 复用（约 5 分钟 TTL，
   单条 query 内多 step 才体现）。

## 怎么读结论

- **cache 命中率低甚至 0**：正常——单条 query、step 少时前缀复用机会小；system+skill 越大、
  多轮越长，命中率越有意义。要对比 cache 收益，跑 `--all` 拉长样本。
- **custom 未命中 > 0**：模型发起了录制里没有的调用（换了参数/分叉）。要么补覆盖该分支的轨迹，
  要么让 query 更贴近原轨迹。严格回放下**绝不喂假数据**，未命中就是未命中。
- **bash 抢戏 = 是**：挂 `agent_toolset_20260701` 后模型绕过 custom tool、跑去沙箱
  `ls/find/扫端口` 找工具。这是本 skill 要实测的历史问题；结论与规避写在 `PROBLEMS.md`。

## 换客户注意

冻结层 `report.cache_hit_rate()` / 报告结构是通用逻辑，不用改。客户特异的两处：
自研侧耗时回调（`run.py` 的 `make_self_side()`，随轨迹结构变）和回放键
（`example-demo/scripts/replay_lib.py` 的 `api_call_key()`）——键定得准，custom 未命中才低，对比才可信。
