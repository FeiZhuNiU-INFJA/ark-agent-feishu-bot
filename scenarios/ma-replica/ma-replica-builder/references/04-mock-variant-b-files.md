# 04 · 变体 B：文件静态 mock（默认方案）

> 这是**默认** mock 方案。除非用户明确要更高保真的性能对比（见 `03-mock-variant-a-custom-tool.md`），
> 否则就用它。

## 思路

最简方案：**不注册任何工具**，改把轨迹里出现过的每次业务调用**物化成一个文件**，
文件内容就是那次调用的返回。这些文件随 skill bundle 一起被 MA **只读挂载到 `/mnt/skills/`**，
模型用内置 `read` 工具读取即可。无需 custom tool、无需客户端常驻、无需公网隧道。

适合：没有常驻客户端时的兜底、或只想做"行为冒烟"（跑通流程、看模型编排是否合理），
保真度低于变体 A（模型不再真正"决策调用工具"，而是被引导去读文件）。

## 文件命名标准

`<method>__<回放键的文件系统安全化>__<8位hash>.txt`

- `method`：工具名（如 `api_call`）。
- 回放键：直接取 `replay_map.json` 里的 key（层③ extract 生成时用客户语义算好，对本步是**不透明字符串**）。
- 安全化：`gen_file_mocks.safe_filename()` 把 `| = ;` → `__`，`, / 空格` → `-`，去掉其它特殊字符，
  过长截断，末尾拼 8 位 hash 防撞。这是纯字符串处理、与客户无关，随冻结转换器一起固定。

## 落位与说明

`gen_file_mocks.py` 是**冻结契约转换器**（层②）：只读 `replay_map.json`，换客户不用改。

```bash
cd scenarios/ma-replica/ma-replica-builder
python scripts/gen_file_mocks.py --out-dir <工作目录>
```

产出 `<工作目录>/mocks-skill/`：
- `mocks/<file>.txt`：每次调用的返回原文。
- `mocks/INDEX.md`：人读「调用键 → 文件」映射表。
- `mocks/manifest.json`：机读映射。
- `SKILL.md`：一个"离线数据台账"skill，正文含**取数规约**。
- 另外在 `<工作目录>/mock_system_appendix.md` 导出一份**可直接粘进 system prompt 的附录**：

  > 本次运行处于离线回放模式：不要调用 `api_call`。所有业务数据已物化到 `/mnt/skills/.../mocks/`。
  > 需要某次结果时先查 `mocks/INDEX.md`，用 read 读对应文件；未列出的查询视为无数据，不要编造。

## 上到 MA（默认路径，已在 run.py 里自动化）

`example-nio/scripts/run.py --mock files`（默认）会自动：把 `mocks-skill/` 用 CreateSkill 上传、
把 `mock_system_appendix.md` 拼进 agent 的 `system`、且**不注册任何 custom tool**。模型即"读文件"
代替"调工具"。手动做也可以，见 `05-build-and-run-ma.md`。
