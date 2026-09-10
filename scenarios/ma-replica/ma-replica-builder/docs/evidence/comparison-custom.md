# MA 复刻 vs 原轨迹 —— 性能对比

> 口径边界：自研侧能否给出 token/cache 取决于客户导出格式；
> 若导出只含消息（无 usage），则 token/cache 仅 MA 单边实测。

## 一、逐条对比

| 轨迹 | 自研耗时(s) | 自研步数 | MA耗时(s) | MA模型请求数 | MA入/出token | MA cache_read | MA cache命中率 | custom未命中 | bash抢戏 |
|---|---|---|---|---|---|---|---|---|---|
| trajectory1.json | 558.354 | 12 | 149.013 | 14 | 521344/3089 | 322408 | 38.21% | 3 | 是 |

## 二、MA 侧汇总

- 累计 input_tokens（未缓存输入）：521344
- 累计 output_tokens：3089
- 累计 cache_read_input_tokens：322408
- 累计 cache_creation_input_tokens：0
- **整体 cache 命中率**：38.21%（= cache_read / (input + cache_read)）

## 三、保真度旁注

- custom tool 未命中总次数：3（>0 说明模型走出了录制轨迹，需补轨迹或收敛 query）。
- bash 抢戏（挂 agent_toolset 后模型用 bash 去沙箱瞎找工具）：检测到，见 runs 里 builtin_tool_calls。

## 四、口径说明

- 自研侧 token/cache 是否可比取决于客户导出是否含 usage；只含消息时不可恢复。
- MA 侧 cache 命中依赖多轮 prefix 复用（约 5 分钟 TTL），单条 query 内多 step 才体现。