---
name: offline-mock-data
description: "离线 mock 数据台账：把客户 Agent 轨迹里出现过的每次业务工具调用物化为文件，供 MA Agent 在离线回放模式下用 read 读取，替代真实工具调用（变体 B）。"
---

# 离线 mock 数据台账

本 skill 承载 10 条录制业务数据（`mocks/` 目录），并规定离线回放模式下的取数方式。

## 离线 mock 数据读取规约（变体 B）

本次运行处于**离线回放**模式：不要调用 `api_call` 或任何外部业务工具。
所有业务数据已预先物化为文件，挂载在只读目录 `/mnt/skills/<本skill>/mocks/` 下。

取数规则：
1. 需要某次 `api_call` 的结果时，先查 `mocks/INDEX.md` 里「调用 -> 文件」映射；
2. 用内置 read 工具读取对应文件，文件内容即该次调用的真实返回；
3. `mocks/INDEX.md` 未列出的查询，视为**无数据**，据实说明，不要编造。

> 台账明细见 [`mocks/INDEX.md`](mocks/INDEX.md)，机读映射见 `mocks/manifest.json`。
