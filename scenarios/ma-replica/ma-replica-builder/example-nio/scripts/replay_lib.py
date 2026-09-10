"""replay_lib.py —— 客户层（NIO）：业务接口回放键 + 严格回放的纯函数。

被同目录的 extract_trajectories.py / run.py 复用。单处定义，避免"抽取端"与"回放端"键规则漂移。

★★★ 全文都是客户特有逻辑：api_call_key() 的字段语义是 NIO 悟空系统的接口形态。
     换客户时按你的接口参数语义重写本文件（而不是加 flag）。 ★★★
自包含，无第三方依赖。
"""
from __future__ import annotations

import hashlib
import json


def api_call_key(args: dict) -> str:
    """为一次业务接口调用生成可回放的稳定键。

    ── 客户特有 ──
    这里的参数字段（object_code / recommend_tag / where.conditions ...）是 NIO 悟空系统的形态。
    换客户时：先看几条轨迹里 api_call 的 params 长什么样，把"决定返回哪行数据"的字段纳入键，
    把"不影响命中的字段"（分页、排序、返回列顺序）忽略掉。

    NIO 规则：
      - 纳入：api_code、object_code / object_code_list、recommend_tag、log_path、query(哈希)、
              where 的 columnCode=value（含 conditions 列表，排序后拼接）。
      - 忽略：columns 顺序、limit / offset、order_by。
    """
    api = args.get("api_code", "")
    p = args.get("params", {}) or {}
    parts = ["api", api]
    if "object_code" in p:
        parts.append("obj=" + str(p["object_code"]))
    if "object_code_list" in p:
        parts.append("objs=" + ",".join(sorted(p["object_code_list"])))
    if "recommend_tag" in p:
        parts.append("tag=" + str(p["recommend_tag"]))
    if "log_path" in p:
        parts.append("log=" + str(p["log_path"]))
    if "query" in p:
        parts.append("q=" + hashlib.sha1(str(p["query"]).encode()).hexdigest()[:10])
    where = p.get("where") or {}
    vals = []
    if isinstance(where, dict):
        if "value" in where:
            vals.append(str(where.get("columnCode")) + "=" + str(where.get("value")))
        for cond in where.get("conditions", []) or []:
            vals.append(str(cond.get("columnCode")) + "=" + str(cond.get("value")))
    if vals:
        parts.append("where=" + ";".join(sorted(vals)))
    return "|".join(parts)


def strict_lookup(replay_map: dict, api_code: str, params: dict) -> tuple[str, bool]:
    """严格回放：命中录制键返回原数据；未命中返回结构化 [tool_error]。

    返回 (输出文本, 是否命中)。未命中时输出错误让模型如实感知"走出录制轨迹"，不喂假数据。
    """
    key = api_call_key({"api_code": api_code, "params": params})
    hit = replay_map.get(key)
    if hit is not None:
        return hit["result"], True
    err = "[tool_error] " + json.dumps({
        "code": "REPLAY_MISS",
        "message": f"该查询未包含在录制轨迹中，严格回放模式下不可用: {key}",
    }, ensure_ascii=False)
    return err, False
