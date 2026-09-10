"""gen_file_mocks.py —— 冻结契约转换器（变体 B）：把每次工具调用物化成文件，做“文件静态 mock”。

冻结层定位：本脚本**只吃中间产物** `replay_map.json`（见 references/00-frozen-vs-client.md
的「中间产物契约」），把每个回放键当**不透明字符串**处理，不认识任何客户接口语义，也不碰原始轨迹。
所以它跨客户可复用、不用改——换客户时变的是"怎么生成 replay_map"（客户层 extract），不是本脚本。

思路：不注册任何工具，改把录制到的每次调用（replay_map.json 的每个键）写成一个文件，
文件名 = 方法名 + 回放键的文件系统安全化 + 8 位 hash，
文件内容 = 该次调用录制的返回原文。这些文件随 skill bundle 一起被 MA 只读挂到 /mnt/skills，
Agent 用内置 read 直接读，无需注册 custom tool、无需公网隧道。

输入（--out-dir，extract 的输出目录）：replay_map.json
输出（--out-dir/mocks-skill/）：
  - SKILL.md          : 一个「离线数据台账」skill，正文=可直接粘进 system prompt 的读文件规约
  - mocks/<file>      : 每次调用的返回原文
  - mocks/INDEX.md    : 人读「调用 -> 文件」映射
  - mocks/manifest.json : 机读映射（键 -> 文件名 / 方法 / 参数）

自包含：只读 --out-dir 下 JSON；不 import 客户层，也不 import 主项目。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re

from case_paths import add_case_args, resolve_shared_dir

SKILL_NAME = "offline-mock-data"
_APPENDIX_TITLE = "## 离线 mock 数据读取规约（变体 B）"


def safe_filename(key: str, prefix: str = "", maxlen: int = 120) -> str:
    """把回放键转成文件系统安全的文件名。

    纯字符串处理、与客户无关（回放键在这里是不透明字符串），故随本转换器一起冻结。
    规则：分隔符 |=; -> __，, / 空格 -> -，其余非字母数字下划线中横线的字符去掉；
    过长则截断并拼 8 位 hash 防撞。
    """
    base = f"{prefix}{key}" if prefix else key
    s = base.replace("|", "__").replace("=", "-").replace(";", "__")
    s = s.replace(",", "-").replace("/", "-").replace(" ", "-")
    s = re.sub(r"[^0-9A-Za-z_\-]", "", s)
    h = hashlib.sha1(base.encode()).hexdigest()[:8]
    if len(s) > maxlen:
        s = s[:maxlen]
    return f"{s}__{h}"


def build_appendix(api_tool: str) -> str:
    """可直接粘进 system prompt 的附录：把工具调用改写成读文件。"""
    return (
        f"{_APPENDIX_TITLE}\n\n"
        f"本次运行处于**离线回放**模式：不要调用 `{api_tool}` 或任何外部业务工具。\n"
        "所有业务数据已预先物化为文件，挂载在只读目录 `/mnt/skills/<本skill>/mocks/` 下。\n\n"
        "取数规则：\n"
        f"1. 需要某次 `{api_tool}` 的结果时，先查 `mocks/INDEX.md` 里「调用 -> 文件」映射；\n"
        "2. 用内置 read 工具读取对应文件，文件内容即该次调用的真实返回；\n"
        "3. `mocks/INDEX.md` 未列出的查询，视为**无数据**，据实说明，不要编造。\n"
    )


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="replay_map.json -> 文件静态 mock（变体 B）")
    add_case_args(ap)
    ap.add_argument("--api-tool", default="api_call", help="业务网关工具名（用于附录文案）")
    return ap.parse_args()


def main() -> None:
    a = parse_args()
    out = resolve_shared_dir(a)
    replay = json.loads((out / "replay_map.json").read_text())

    skill_dir = out / "mocks-skill"
    mocks_dir = skill_dir / "mocks"
    mocks_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {}
    used_names: set[str] = set()
    index_rows = []

    for key, rec in sorted(replay.items()):
        method = rec.get("name", "tool")
        fname = safe_filename(key, prefix=f"{method}__") + ".txt"
        # 极端撞名兜底（safe_filename 已带 hash，正常不会触发）
        while fname in used_names:
            fname = safe_filename(key + "#", prefix=f"{method}__") + ".txt"
        used_names.add(fname)

        result = rec.get("result", "")
        (mocks_dir / fname).write_text(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))

        manifest[key] = {
            "file": f"mocks/{fname}",
            "method": method,
            "args": rec.get("args", {}),
            "is_error": rec.get("is_error", False),
        }
        flag = " ⚠️error" if rec.get("is_error") else ""
        index_rows.append(f"| `{key}` | `mocks/{fname}` |{flag} |")

    (mocks_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    index = ["# 离线 mock 数据台账（调用 -> 文件）\n",
             f"共 {len(manifest)} 条录制调用。读取方式见本 skill 的 SKILL.md。\n",
             "| 调用键 | 文件 | 备注 |", "|---|---|---|", *index_rows, ""]
    (mocks_dir / "INDEX.md").write_text("\n".join(index))

    desc = ("离线 mock 数据台账：把客户 Agent 轨迹里出现过的每次业务工具调用物化为文件，"
            "供 MA Agent 在离线回放模式下用 read 读取，替代真实工具调用（变体 B）。")
    skill_md = (f"---\nname: {SKILL_NAME}\n"
                f"description: \"{desc}\"\n---\n\n"
                f"# 离线 mock 数据台账\n\n"
                f"本 skill 承载 {len(manifest)} 条录制业务数据（`mocks/` 目录），"
                f"并规定离线回放模式下的取数方式。\n\n"
                f"{build_appendix(a.api_tool)}\n"
                f"> 台账明细见 [`mocks/INDEX.md`](mocks/INDEX.md)，机读映射见 `mocks/manifest.json`。\n")
    (skill_dir / "SKILL.md").write_text(skill_md)

    # 单独导出一份可粘进 system prompt 的附录，方便变体 B 直接拼到 system
    (out / "mock_system_appendix.md").write_text(build_appendix(a.api_tool))

    errs = sum(1 for v in manifest.values() if v["is_error"])
    print(f"OK 物化 {len(manifest)} 条调用 -> {mocks_dir}（其中错误返回 {errs} 条）")
    print(f"  skill: {skill_dir / 'SKILL.md'}")
    print(f"  台账:  {mocks_dir / 'INDEX.md'}")
    print(f"  附录:  {out / 'mock_system_appendix.md'}")


if __name__ == "__main__":
    main()
