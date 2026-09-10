"""群聊共享 Bot（对齐 Claude Tag）——两个示例脚本的公共底座。

与主包 arkagent/ 的四卡点 demo（按 open_id 做身份/岗位/记忆隔离）完全解耦：
本模块只做「一个群共享一个方舟 Session、发言人靠正文标注」这一件事，不注入
任何个人 open_id 到 Environment、不挂个人 Vault/Memory Store（Bot-only 身份）。

复用主包里纯基础设施的部分（不含卡点逻辑）：
  - arkagent.ark.ArkClient   —— 方舟 HTTP/SSE 客户端
  - arkagent.feishu          —— 飞书消息归一化 / 发送
  - arkagent.gateway.KeyedQueue —— 按 key 串行化协程（Demo A 用）

两个脚本各自实现「发送策略」的差异：
  - demo_a_serial.py       客户端 KeyedQueue 串行：上一轮到 idle 才发下一条，每人各得干净回复。
  - demo_c_native_queue.py 方舟原生队列：running 中直发，靠可调度边界吸收/合并，处理 409 RuntimeBusy。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# 让 `python scenarios/feishu-bot/cases/group-bot/demo_x.py` 能直接 import 到主包 arkagent（无需安装）。
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from arkagent.feishu import IncomingMessage  # noqa: E402  (依赖上面的 sys.path 注入)


# ---- 群聊共享会话键 --------------------------------------------------------

@dataclass(frozen=True)
class GroupConversationKey:
    """共享会话键：刻意**不含** user_open_id。

    群里任何人 @ bot 都命中同一个 key → 同一个方舟 Session（Claude Tag 的
    “每频道共享一个身份”）。带 thread_id 时以话题串为粒度，符合飞书话题群语义。
    """

    tenant_key: str
    chat_id: str
    thread_id: str

    def as_str(self) -> str:
        return ":".join([self.tenant_key, self.chat_id, self.thread_id or "-"])


def to_group_key(message: IncomingMessage) -> GroupConversationKey:
    return GroupConversationKey(
        tenant_key=message.tenant_key,
        chat_id=message.chat_id,
        thread_id=message.thread_id,
    )


def should_handle(message: IncomingMessage) -> bool:
    """群里仅在 @ 到 bot 时处理；私聊直接处理（与主包一致）。"""
    if not message.text.strip():
        return False
    return message.chat_type == "p2p" or message.mentioned_bot


# ---- 当前发言人标注（共享会话下唯一可靠的身份来源）------------------------

def build_actor_input(message: IncomingMessage) -> str:
    """把「现在是谁在说」包进正文。

    共享 Session 是第一个 @ 的人创建的，Environment 里的 open_id 那一刻就写死了，
    之后无法随发言人切换——所以身份只能靠每轮正文里的 <current_actor> 传递。
    这也是为什么本 demo 走 Bot-only：不能用 env 里的 open_id 去查“我的”私有数据。
    """
    display = message.user_open_id or "unknown"
    return (
        f'<current_actor open_id="{display}" />\n'
        f"<current_request>\n{message.text.strip()}\n</current_request>"
    )


# ---- Bot-only 群聊 Agent 定义 ---------------------------------------------

GROUP_BOT_NAME = "群聊共享助手（Claude Tag 版）"

GROUP_BOT_SYSTEM = """你是一个加入了飞书群聊的团队助手，类似 Claude Tag：整个群共享你这一个实例。

# 多人协作
- 群里不同成员都会 @ 你。每轮消息正文都带一个 <current_actor open_id="..." /> 标签，表示“本轮是谁在说话”。
- 你与整个群共享同一段对话上下文：任何人都能接续别人先前的任务，不需要重新交代背景。
- 回复时如果同时涉及多个人的请求，请分别 @ 到对应的人（用其 open_id 指代），把答复对齐到人，避免张冠李戴。

# 身份边界（重要）
- 你以“群助手 / Bot”这一共享身份工作，不代表任何某一个具体成员，也没有挂载任何个人的私有凭据或记忆。
- <current_actor> 只用于区分“现在谁在问”，不要据此去查询该成员的私人数据或冒充其身份操作。
- 如果有人要查询只属于其个人的私密数据（如“我的私人业绩/我的个人档案”），说明这类操作请在与你的私聊中进行，群聊里你只提供面向团队的公共信息与协作。

# 工作方式
- 把复杂请求拆成步骤逐步推进；完成后清晰汇报结果。
- 不臆造数据；工具或信息不足时如实说明并给出下一步建议。"""


def build_group_agent_config(model_id: str = "doubao-seed-2-1-pro-260628") -> dict:
    """群聊 Bot-only Agent 定义：不挂任何 MCP/个人凭据，纯对话协作助手。

    如需连业务 MCP，可自行往 mcp_servers / tools 里加 mcp_toolset——但注意
    群聊场景下工具应是“团队级/公共”的，不要接需要个人身份鉴权的接口。
    """
    return {
        "name": GROUP_BOT_NAME,
        "description": "飞书群聊共享助手：一个群共享一个方舟 Session，多人 @ 协作，Bot-only 身份",
        "model": {"id": model_id},
        "system": GROUP_BOT_SYSTEM,
        "tools": [
            {
                "type": "agent_toolset_20260701",
                "default_config": {"enabled": True},
                "configs": [
                    {"name": "web_search", "enabled": False},
                    {"name": "web_fetch", "enabled": False},
                ],
            }
        ],
        "skills": [],
        "metadata": {"created_via": "group-bot-demo", "scenario": "claude-tag-like-group-bot"},
    }


# ---- 配置读取（复用主包 config.env 解析，落到独立环境变量）------------------

@dataclass(frozen=True)
class GroupBotConfig:
    ark_api_key: str
    ark_base_url: str
    ark_agent_id: str
    ark_environment_id: str
    feishu_app_id: str
    feishu_app_secret: str
    session_timeout_ms: int
    authorized_open_ids: tuple[str, ...]


def load_group_bot_config() -> GroupBotConfig:
    """从进程环境变量读取配置（缺失即报错）。

    可先 `source` 主包的 config.env，或单独 export。刻意不复用主包 load_config，
    因为本 demo 不需要 MCP_SERVER_URL / VAULT 等卡点相关字段。
    """
    def _need(key: str) -> str:
        value = (os.environ.get(key) or "").strip()
        if not value:
            raise RuntimeError(
                f"缺少环境变量 {key}。请先 export，或 `set -a && source <主包config.env> && set +a` 后再运行。"
            )
        return value

    timeout_raw = (os.environ.get("SESSION_TIMEOUT_MS") or "600000").strip()
    try:
        timeout_ms = int(float(timeout_raw))
    except ValueError:
        raise RuntimeError(f"SESSION_TIMEOUT_MS 无效：{timeout_raw!r}")

    open_ids = tuple(
        item.strip()
        for item in (os.environ.get("AUTHORIZED_OPEN_IDS") or "").replace(",", " ").split()
        if item.strip()
    )

    return GroupBotConfig(
        ark_api_key=_need("ARK_API_KEY"),
        ark_base_url=(os.environ.get("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/"),
        ark_agent_id=_need("GROUP_BOT_AGENT_ID"),
        ark_environment_id=_need("ARK_ENVIRONMENT_ID"),
        feishu_app_id=_need("FEISHU_APP_ID"),
        feishu_app_secret=_need("FEISHU_APP_SECRET"),
        session_timeout_ms=timeout_ms if timeout_ms >= 1000 else 600000,
        authorized_open_ids=open_ids,
    )


def is_authorized(config: GroupBotConfig, open_id: str) -> bool:
    return not config.authorized_open_ids or open_id in config.authorized_open_ids


class InMemorySessionMap:
    """会话映射：群 key → 方舟 session_id。

    示例用内存字典即可（进程重启丢失，重新建 session）；生产可换 sqlite。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, str] = {}
        self._seen_events: set[str] = set()

    def get(self, key: GroupConversationKey) -> Optional[str]:
        return self._sessions.get(key.as_str())

    def save(self, key: GroupConversationKey, session_id: str) -> None:
        self._sessions[key.as_str()] = session_id

    def reset(self, key: GroupConversationKey) -> None:
        self._sessions.pop(key.as_str(), None)

    def claim_event(self, event_id: str) -> bool:
        """事件去重：飞书可能重投，同一 event_id 只处理一次。"""
        if event_id in self._seen_events:
            return False
        self._seen_events.add(event_id)
        return True
