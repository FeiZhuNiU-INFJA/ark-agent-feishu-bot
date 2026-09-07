"""Demo A：客户端串行（KeyedQueue）——每人各得一条干净回复。

思路（对应方案 A）：
  - 群里所有人 @ bot 共享同一个方舟 Session（to_group_key 抹掉了 user_open_id）。
  - 用 KeyedQueue 按群 key 串行：**上一轮跑到 idle（end_turn）才发下一条**，
    因此每次 POST 时 Session 都是空闲的，从根上不进方舟的“运行中待处理队列”，
    不会发生消息合并，也不会触发 409 RuntimeBusy —— 每条消息各自独立成轮、
    各得一条清清楚楚回给发问人的答复。
  - 代价：后到的人要排队。排队期间给一句“正在处理，请稍候”的可见回执
    （类似 Claude Tag 的 OnIt 表情）。

运行：
  set -a && source ~/.arkagent/config.env && set +a   # 或自行 export 相关变量
  export GROUP_BOT_AGENT_ID=<用 create_group_agent.py 建出的 agent id>
  python examples/group_bot/demo_a_serial.py
"""
from __future__ import annotations

import asyncio
import logging
import threading

from shared import (  # 同目录脚本，直接导入
    GroupBotConfig,
    GroupConversationKey,
    InMemorySessionMap,
    build_actor_input,
    is_authorized,
    load_group_bot_config,
    should_handle,
    to_group_key,
)

# shared 已把仓库根加入 sys.path，这里能 import 到主包基础设施。
from arkagent.ark import ArkClient, RunResult
from arkagent.feishu import FeishuSender, IncomingMessage, start_feishu_gateway
from arkagent.gateway import KeyedQueue

log = logging.getLogger("group_bot.demo_a")


class SerialGroupBot:
    """客户端串行版群聊 bot。accept() 由 WS 线程调用，处理协程投递到事件循环。"""

    def __init__(
        self,
        config: GroupBotConfig,
        ark: ArkClient,
        sender: FeishuSender,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._config = config
        self._ark = ark
        self._sender = sender
        self._loop = loop
        self._sessions = InMemorySessionMap()
        self._queue = KeyedQueue()

    # WS 线程入口：只做去重 + 投递，满足飞书 3 秒约束。
    def accept(self, message: IncomingMessage) -> bool:
        if not should_handle(message):
            return False
        if not self._sessions.claim_event(message.event_id):
            return False
        key = to_group_key(message)

        def _enqueue() -> None:
            # KeyedQueue 保证同一群 key 的任务按到达顺序串行执行。
            self._queue.enqueue(key.as_str(), lambda: self._run(message, key))

        self._loop.call_soon_threadsafe(_enqueue)
        return True

    async def _reply(self, message: IncomingMessage, text: str) -> None:
        # 群里回复到原消息（reply），私聊直接发到会话。lark-oapi 是同步调用，丢到 executor。
        if message.chat_type == "group" and message.message_id:
            await self._loop.run_in_executor(None, self._sender.reply, message.message_id, text)
        else:
            await self._loop.run_in_executor(None, self._sender.send_to_chat, message.chat_id, text)

    async def _run(self, message: IncomingMessage, key: GroupConversationKey) -> None:
        try:
            await self._process(message, key)
        except Exception as error:  # noqa: BLE001 - 兜底回执，避免一条失败拖垮队列
            log.exception("处理消息失败")
            await self._reply(message, f"执行失败：{str(error)[:240]}")

    async def _process(self, message: IncomingMessage, key: GroupConversationKey) -> None:
        if not is_authorized(self._config, message.user_open_id):
            await self._reply(message, "当前用户未授权。请联系管理员把你的 open_id 加入白名单。")
            return

        if message.text.strip() == "/new":
            self._sessions.reset(key)
            await self._reply(message, "已重置本群会话，下一条消息会创建新的共享 Session。")
            return

        session_id = self._sessions.get(key)
        if not session_id:
            await self._reply(message, "已收到，正在为本群创建共享会话，首次可能需要几分钟。")
            session_id = await self._ark.create_session(
                self._config.ark_agent_id,
                self._config.ark_environment_id,
                # Bot-only：不注入任何个人 open_id、不挂个人 Vault/Memory Store。
            )
            self._sessions.save(key, session_id)
        else:
            # 已有会话说明可能在排队（前一轮刚跑完）；给个“正在处理”的可见回执。
            await self._reply(message, "已收到，正在处理，请稍候。")

        # 关键：串行模式下发消息时 Session 一定是 idle 的，这一轮独立处理、独立回复。
        actor_input = build_actor_input(message)
        result: RunResult = await self._ark.run(
            session_id, actor_input, self._config.session_timeout_ms
        )
        await self._reply(message, _result_to_text(result))


def _result_to_text(result: RunResult) -> str:
    if result.terminal == "failed":
        raise RuntimeError("Agent Session 执行失败")
    if not result.messages:
        raise RuntimeError("Agent Session 已结束，但没有产生回复")
    return result.messages[-1]


def main() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = load_group_bot_config()

    ark = ArkClient(config.ark_api_key, config.ark_base_url)
    sender = FeishuSender(config.feishu_app_id, config.feishu_app_secret)

    loop = asyncio.new_event_loop()
    bot = SerialGroupBot(config, ark, sender, loop)
    threading.Thread(target=loop.run_forever, name="group-bot-loop", daemon=True).start()

    print("Demo A（客户端串行）已启动：")
    print(f"- 飞书 App ID：{config.feishu_app_id}")
    print(f"- 群聊共享 Agent ID：{config.ark_agent_id}")
    print("- 策略：同一群/话题串行处理，每人各得独立回复；后到的消息排队。")
    print("在群里 @ 这个 bot 试试（多人先后 @，观察逐条独立回复）。指令：/new 重置本群会话。")
    start_feishu_gateway(config.feishu_app_id, config.feishu_app_secret, bot)


if __name__ == "__main__":
    main()
