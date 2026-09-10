"""report.py —— 冻结层：MA 侧指标聚合 + 对比报告生成（永不随客户变）。

MA 侧的口径是平台固定的：model_usage 四件套、cache 命中率算法、逐条/汇总表结构。
唯一「客户特异」的是**自研侧耗时怎么从轨迹里数出来**——不同客户轨迹结构不同，
所以那部分由调用方传入一个 self_side(traj_name) -> (耗时, 步数) 的回调，本文件不假设轨迹结构。

用法（客户样板里）：
    from report import build_report
    build_report(runs_dir, out_md, self_side=my_duration_fn)
"""
from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Callable, Optional

# self_side 回调：给轨迹文件名，返回 (自研耗时秒, 自研步数)；拿不到就返回 (None, None)。
SelfSideFn = Callable[[str], "tuple[Optional[float], Optional[int]]"]


def cache_hit_rate(u: dict) -> float:
    """MA 官方口径：cache_read / (未缓存 input + cache_read)。分母 0 时返回 0。"""
    inp = u.get("input_tokens", 0) or 0
    cr = u.get("cache_read_input_tokens", 0) or 0
    denom = inp + cr
    return round(cr / denom, 4) if denom else 0.0


def _normalize(run: dict, rf_stem: str) -> dict:
    """把一条 run.json 归一成统一视图，兼容两种落盘格式：

    - 新格式（并发重复聚合）：含 repeats/ok_count/fail_ratio/agg_ok（agg_ok 为成功 rep 的均值）。
    - 旧格式（单次实跑）：含 wall_clock_s/usage_total（视作 repeats=1，成功与否看有无 usage）。

    统一输出：{traj, repeats, ok_count, fail_ratio, wall_clock_s, model_requests,
              usage(仅成功均值), custom_miss, snoop}。全失败时耗时/token 记 None。
    """
    traj = run.get("trajectory") or (rf_stem + ".json")
    if "agg_ok" in run or "fail_ratio" in run:      # 新聚合格式
        agg = run.get("agg_ok") or {}
        u = agg.get("usage_total") or {}
        return {
            "traj": traj,
            "repeats": run.get("repeats", 1),
            "ok_count": run.get("ok_count", 0),
            "fail_ratio": run.get("fail_ratio", 0.0),
            "wall_clock_s": agg.get("wall_clock_s"),
            "model_requests": agg.get("model_requests"),
            "usage": u,
            "custom_miss": run.get("custom_miss_total", 0),
            "snoop": run.get("bash_snoop_any", False),
        }
    # 旧单次格式
    ok = bool(run.get("ok", (run.get("model_requests") or 0) > 0))
    return {
        "traj": traj,
        "repeats": 1,
        "ok_count": 1 if ok else 0,
        "fail_ratio": 0.0 if ok else 1.0,
        "wall_clock_s": run.get("wall_clock_s") if ok else None,
        "model_requests": run.get("model_requests") if ok else None,
        "usage": run.get("usage_total", {}) if ok else {},
        "custom_miss": len(run.get("custom_tool_misses", [])),
        "snoop": run.get("bash_snoop_detected", False),
    }


def _fmt(v) -> str:
    return "N/A" if v is None else (f"{v}")


def build_report(runs_dir: Path, out_md: Path,
                 self_side: Optional[SelfSideFn] = None) -> dict:
    """读 runs_dir/<traj>/run.json（ma_runtime 落盘），产出对比报告 md，返回汇总 dict。

    self_side 为 None 时，自研侧列全部标 N/A（例如 token/cache 本就不可恢复的场景）。
    统计口径（按用户要求）：失败的 rep 不计入耗时/token（均值只用成功 rep），但单列失败比例作参考。
    兼容旧布局：也认 runs_dir/*.json（每条轨迹一个平铺文件）。
    """
    run_files = sorted(glob.glob(str(runs_dir / "*" / "run.json")))
    if not run_files:                       # 向后兼容旧的平铺 <stem>.json 布局
        run_files = sorted(glob.glob(str(runs_dir / "*.json")))
    if not run_files:
        raise SystemExit(f"未找到 MA 实跑结果于 {runs_dir}（先用 ma_runtime 跑一遍）")

    lines = [
        "# MA 复刻 vs 原轨迹 —— 性能对比\n",
        "> 口径边界：自研侧能否给出 token/cache 取决于客户导出格式；",
        "> 若导出只含消息（无 usage），则 token/cache 仅 MA 单边实测。",
        "> 每条轨迹并发重复多次；**失败的重复不计入耗时/token 均值**，仅统计失败率作参考。\n",
        "## 一、逐条对比（MA 侧数值=成功重复的均值）\n",
        "| 轨迹 | 自研耗时(s) | 自研步数 | MA均耗时(s) | 成功/重复 | 失败率 | "
        "MA均模型请求数 | MA均入/出token | MA均cache_read | MA cache命中率 | custom未命中 | bash抢戏 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    agg = {"input": 0.0, "output": 0.0, "cache_read": 0.0, "cache_create": 0.0}
    any_snoop = False
    total_miss = 0
    total_reps = 0
    total_fail = 0

    for rf in run_files:
        run = json.loads(Path(rf).read_text())
        n = _normalize(run, Path(rf).parent.name if Path(rf).name == "run.json" else Path(rf).stem)
        self_dur, self_steps = (self_side(n["traj"]) if self_side else (None, None))

        u = n["usage"] or {}
        hr = cache_hit_rate(u)
        # 只有该轨迹有成功 rep 才把其（均值）计入总量
        if n["ok_count"] > 0:
            agg["input"] += u.get("input_tokens", 0) or 0
            agg["output"] += u.get("output_tokens", 0) or 0
            agg["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
            agg["cache_create"] += u.get("cache_creation_input_tokens", 0) or 0
        total_miss += n["custom_miss"]
        total_reps += n["repeats"]
        total_fail += (n["repeats"] - n["ok_count"])
        any_snoop = any_snoop or n["snoop"]

        io = (f"{_fmt(u.get('input_tokens'))}/{_fmt(u.get('output_tokens'))}"
              if n["ok_count"] > 0 else "N/A")
        lines.append(
            f"| {n['traj']} | {self_dur if self_dur is not None else 'N/A'} | "
            f"{self_steps if self_steps is not None else 'N/A'} | "
            f"{_fmt(n['wall_clock_s'])} | {n['ok_count']}/{n['repeats']} | "
            f"{n['fail_ratio']:.0%} | {_fmt(n['model_requests'])} | {io} | "
            f"{_fmt(u.get('cache_read_input_tokens'))} | {hr:.2%} | {n['custom_miss']} | "
            f"{'是' if n['snoop'] else '否'} |")

    total_hr = cache_hit_rate({"input_tokens": agg["input"],
                               "cache_read_input_tokens": agg["cache_read"]})
    overall_fail = round(total_fail / total_reps, 4) if total_reps else 0.0
    lines += [
        "\n## 二、MA 侧汇总（各轨迹成功均值之和）\n",
        f"- 累计 input_tokens（未缓存输入）：{agg['input']:.0f}",
        f"- 累计 output_tokens：{agg['output']:.0f}",
        f"- 累计 cache_read_input_tokens：{agg['cache_read']:.0f}",
        f"- 累计 cache_creation_input_tokens：{agg['cache_create']:.0f}",
        f"- **整体 cache 命中率**：{total_hr:.2%}（= cache_read / (input + cache_read)）",
        f"- **整体失败率**：{overall_fail:.2%}（失败重复 {total_fail} / 总重复 {total_reps}；失败不计入上面均值）\n",
        "## 三、保真度旁注\n",
        f"- custom tool 未命中总次数：{total_miss}（>0 说明模型走出了录制轨迹，需补轨迹或收敛 query）。",
        f"- bash 抢戏（挂 agent_toolset 后模型用 bash 去沙箱瞎找工具）："
        f"{'检测到，见 runs 里 builtin_tool_calls' if any_snoop else '未检测到'}。",
        "\n## 四、口径说明\n",
        "- 每条轨迹并发重复多次；MA 侧数值为**成功重复的均值**，失败重复只进失败率、不进均值。",
        "- 自研侧 token/cache 是否可比取决于客户导出是否含 usage；只含消息时不可恢复。",
        "- MA 侧 cache 命中依赖多轮 prefix 复用（约 5 分钟 TTL），单条 query 内多 step 才体现。",
    ]

    out_md.write_text("\n".join(lines))
    summary = {"agg": agg, "total_hit_rate": total_hr, "overall_fail_ratio": overall_fail,
               "total_miss": total_miss, "any_snoop": any_snoop}
    print(f"OK 对比报告 -> {out_md}")
    print(f"  MA 累计 in/out/cache_read = {agg['input']:.0f}/{agg['output']:.0f}/{agg['cache_read']:.0f}  "
          f"命中率={total_hr:.2%}  失败率={overall_fail:.2%}  custom未命中={total_miss}  "
          f"bash抢戏={'是' if any_snoop else '否'}")
    return summary
