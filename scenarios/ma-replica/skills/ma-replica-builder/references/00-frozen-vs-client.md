# 00 · 三层结构：哪些代码可复用、哪些要现写

## 一把尺子

判断某段代码该不该固定成"直接用"的脚本，只问一句：

> **它依赖的是「MA 平台的形状」、「我们自定义的中间产物形状」，还是「这个客户轨迹/工具的形状」？**

前两者都是我们能钉死的契约，天然可复用 → **冻结**。只有第三种每个客户都不一样、加 `--flag`
也盖不住（比如某客户轨迹顶层不是 `messages[]`、或用 Anthropic content blocks 而非 OpenAI
`tool_calls`、或接口参数语义完全不同）→ **不冻结**，分析完该客户轨迹后**现写生成**。

这把尺子把本 skill 切成**三层**：

```
① 冻结·平台运行时   scripts/ark_min.py · ma_runtime.py · report.py     依赖 MA 平台
                          ▲ 传 custom_tools / resolve / self_side 回调
② 冻结·契约转换器   scripts/build_skill_bundle.py · gen_file_mocks.py  只依赖中间产物契约
                          ▲ 读 skill_bodies.json / replay_map.json
─────────────── 中间产物契约（下面钉死的那几个 JSON） ───────────────
                          ▲ 由客户层生成
③ 客户·生成式代码   example-demo/scripts/extract_trajectories.py ·     依赖客户轨迹
                    replay_lib.py · run.py 的工具面三函数
```

关键洞察：**真正跨客户复用的资产不是某个脚本，而是层②③之间的「中间产物契约」。**
一旦这个契约钉死，所有"只吃中间产物、不碰原始轨迹"的转换器就与客户无关，可以冻结；
真正要现写的只剩"把这个客户的原始轨迹 → 中间产物"这一段。

## 中间产物契约（层②③的边界，务必稳定）

层③的 extract 必须产出下列文件；层②与层①只认这些形状，**不认识任何客户接口语义**：

| 文件 | 形状 | 谁消费 |
|---|---|---|
| `system_prompt.txt` | system prompt 全文（纯文本） | 层① 建 agent 的 `system` |
| `skill_bodies.json` | `{key: {skill_code, document_key, result, is_error}}` | 层② `build_skill_bundle.py` |
| `replay_map.json` | `{key: {name, args, result, is_error, source}}`，key 对下游是**不透明字符串** | 层② `gen_file_mocks.py`；层③ `run.py` 的 resolve |
| `queries.json` | `[{trajectory, query}]` | 层① 重跑的输入样本 |
| `index.json` | `{skill_code: {dir, title, docs[], missing[]}}`（build 产出） | 层① 上传 skill |

> `replay_map.json` 的 key 由客户层用**客户接口语义**算出来（本样例在 `replay_lib.api_call_key()`），
> 但一经写入，层②只把它当字符串做文件名安全化、层③ resolve 只拿它查表 —— 语义不外泄，所以下游能冻结。

## 层① 冻结·平台运行时 `scripts/`（依赖 MA 平台）

| 文件 | 职责 | 为什么能冻结 |
|---|---|---|
| `ark_min.py` | 最小 MA HTTP 客户端：鉴权 / endpoint / SSE 事件流 / CreateSkill / 建删资源 | 全是 MA 平台契约 |
| `ma_runtime.py` | 运行引擎：上传 skill、建 agent/env/session、事件循环、指标累计、清理 | 事件类型、指标字段都是平台固定 |
| `report.py` | 对比报告：MA 侧指标聚合 + cache 命中率算法 + 报告结构 | MA 侧口径平台固定 |

`ma_runtime` / `report` 把"客户特异"的部分外置成**参数/回调**，所以自身能保持通用：

- `ma_runtime.run_session(..., custom_tools=<客户声明>, resolve=<客户回调>)`
- `report.build_report(..., self_side=<客户轨迹耗时回调>)`

## 层② 冻结·契约转换器 `scripts/`（只依赖中间产物契约）

| 文件 | 吃什么 | 为什么能冻结 |
|---|---|---|
| `build_skill_bundle.py` | `skill_bodies.json` → Claude Skills `SKILL.md` 树 + `index.json` | 只认契约字段；剥加载器头部的 `strip_meta_header` 在头部缺省时优雅退化 |
| `gen_file_mocks.py` | `replay_map.json` → 变体 B 文件 mock（含 `safe_filename` 文件名安全化） | key 当不透明字符串处理；`--api-tool` 只用于附录文案 |

> 这两个曾经放在 `example-demo/scripts/`，是历史误置。它们从不读原始轨迹，只读契约，
> 所以上升进冻结层——**换客户直接调用，不用改**。

## 层③ 客户·生成式代码 `example-demo/scripts/`（依赖客户轨迹，现写）

**不是"复制模板改几行"，而是"读懂这个客户的轨迹后，照 example-demo 现写"。**
`example-demo/` 是一份**参照实现**（合成的客服工单样例），示范"层③应该长什么样、产出什么契约"，不是可配置的通用件。

| 文件 | 客户特异在哪 |
|---|---|
| `extract_trajectories.py` | 认这个客户的原始 JSON 结构、工具角色（见 `07-tool-roles.md`），产出上面那套契约 |
| `replay_lib.py` | `api_call_key()` = 客户接口"哪些参数决定返回哪行数据"的语义（写入 replay_map 的 key） |
| `run.py` | **只写三小块**：`build_custom_tools()`（工具声明）+ `make_resolve()`（结果路由）+ `make_self_side()`（轨迹耗时），其余调层①冻结件 |

## 换客户的标准流程

1. 读 `references/` 弄懂方法论与中间产物契约。
2. **打开新客户的轨迹**，看清：顶层结构、工具调用放在哪个字段、有没有 `usage`、加载器/网关/取时间
   分别叫什么名字（`07-tool-roles.md`）。
3. 照 `example-demo/scripts/` **现写**层③：`extract` 认这个客户的结构并吐出契约、`replay_lib.api_call_key()`
   定这个客户的键语义、`run.py` 的三函数给这个客户的工具面。
4. 层① + 层② `scripts/` **原样调用**，不改：
   `build_skill_bundle` / `gen_file_mocks` 吃你产出的契约，`ma_runtime` / `report` 跑 MA。

> 反面教训：不要试图给 `extract` 加一堆 `--flag` 去"配置化"适配所有客户。flag 盖得住"改个工具名"，
> 盖不住"换个轨迹结构"。层③就让它现写，这比一个越长越复杂、还是覆盖不全的配置层更健康——
> 而只要产出的**契约稳定**，层②所有转换器都能白嫖复用。
