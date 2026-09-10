"""Demo C：方舟原生队列（运行中直发 + 吸收/合并）——更接近 Claude Tag 的异步协作。

思路（对应方案 C，依据 common/docs/火山方舟_ManagedAgents_docs.md「运行中继续发送消息」L3183+）：
  - 群里所有人 @ bot 共享同一个方舟 Session。
  - **不在客户端排队**：消息一到就 send_message 直接打进 Session，哪怕它还在 running。
    方舟把它写入「运行中待处理队列」，等 Agent 执行到「可调度边界」（模型请求结束 /
    工具结果返回 / 回合结束）再送入后续模型请求。
  - 由此带来「吸收/合并」：同一边界前堆积的多条消息可能被合并进一次模型请求，
    Agent 不保证为每条消息各回一条（L3193）。适合“同一件事多人接力补充”，
    代价是并发问不同事时回复可能揉在一起。
  - 待处理队列满会返回 409 RuntimeBusy（L3195）：不能猛重试，需退避。

与 Demo A 的关键区别：
  - A：客户端 KeyedQueue 串行，上一轮 idle 才发下一条，每人各得干净回复、无 409。
  - C：直发，靠方舟侧队列吸收合并；用一个常驻事件流消费协程把回复回到群里。

回复策略：因为可能合并、一条回复可能同时面向多人，这里回到**群会话**（不 reply
到某条消息），并靠 system prompt 要求 Agent 分别 @ 到对应的人。

运行：
  set -a && source ~/.arkagent/config.env && set +a
  export GROUP_BOT_AGENT_ID=<用 create_group_agent.py 建出的 agent id>
  python scenarios/feishu-bot/cases/group-bot/demo_c_native_queue.py
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading

from shared import (
    GroupBotConfig,
    GroupConversationKey,
    InMemorySessionMap,
    build_actor_input,
    is_authorized,
    load_group_bot_config,
    should_handle,
    to_group_key,
)

from arkagent.ark import ArkClient, ArkError, event_text
from arkagent.feishu import FeishuSender, IncomingMessage, start_feishu_gateway

log = logging.getLogger("group_bot.demo_c")

MAX_409_RETRIES = 5
BACKOFF_BASE_S = 2.0
BACKOFF_CAP_S = 15.0


def _is_runtime_busy(error: Exception) -> bool:
    """方舟队列满会返回 409 RuntimeBusy。ArkClient 把状态码/报文拼进异常字符串，
    这里按字符串识别（示例够用；生产建议让客户端透出结构化状态码）。"""
    text = str(error)
    return " 409" in text or "RuntimeBusy" in text


class ConcurrentGroupBot:
    """方舟原生队列版：消息直发，不在客户端排队；每个 Session 一个常驻消费协程。"""

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
        # 每个群 key 一个「建会话锁」，避免并发首条消息重复建 Session。
        self._create_locks: dict[str, asyncio.Lock] = {}
        self._consumers: dict[str, asyncio.Task] = {}

    def accept(self, message: IncomingMessage) -> bool:
        if not should_handle(message):
            return False
        if not self._sessions.claim_event(message.event_id):
            return False
        # 直接投递处理协程（不串行化）——多条消息可并发进入 _handle。
        self._loop.call_soon_threadsafe(
            lambda: self._loop.create_task(self._handle(message))
        )
        return True

    async def _send_to_chat(self, chat_id: str, text: str) -> None:
        await self._loop.run_in_executor(None, self._sender.send_to_chat, chat_id, text)

    async def _handle(self, message: IncomingMessage) -> None:
        try:
            if not is_authorized(self._config, message.user_open_id):
                await self._send_to_chat(message.chat_id, "当前用户未授权。请联系管理员把你的 open_id 加入白名单。")
                return

            key = to_group_key(message)
            if message.text.strip() == "/new":
                self._sessions.reset(key)
                await self._stop_consumer(key)
                await self._send_to_chat(message.chat_id, "已重置本群会话，下一条消息会创建新的共享 Session。")
                return

            session_id = await self._ensure_session(message, key)
            await self._post_message(session_id, message)
        except Exception as error:  # noqa: BLE001
            log.exception("处理消息失败")
            await self._send_to_chat(message.chat_id, f"执行失败：{str(error)[:240]}")

    async def _ensure_session(self, message: IncomingMessage, key: GroupConversationKey) -> str:
        lock = self._create_locks.setdefault(key.as_str(), asyncio.Lock())
        async with lock:
            session_id = self._sessions.get(key)
            if session_id:
                return session_id
            await self._send_to_chat(message.chat_id, "已收到，正在为本群创建共享会话，首次可能需要几分钟。")
            session_id = await self._ark.create_session(
                self._config.ark_agent_id,
                self._config.ark_environment_id,
                # Bot-only：不注入个人 open_id、不挂个人 Vault/Memory。
            )
            self._sessions.save(key, session_id)
            # 起一个常驻消费协程读事件流，把 Agent 回复回到群里。
            self._consumers[key.as_str()] = self._loop.create_task(
                self._consume(session_id, message.chat_id, key)
            )
            return session_id

    async def _post_message(self, session_id: str, message: IncomingMessage) -> None:
        """直发 user.message；running 时方舟写入待处理队列。满队列 409 则退避重试。"""
        actor_input = build_actor_input(message)
        delay = BACKOFF_BASE_S
        for attempt in range(MAX_409_RETRIES + 1):
            try:
                await self._ark.send_message(session_id, actor_input)
                return
            except ArkError as error:
                if not _is_runtime_busy(error) or attempt == MAX_409_RETRIES:
                    raise
                # 队列满：不要猛重试。退避等待 Agent 消费掉队列后再发。
                log.info("队列忙(409)，第 %d 次退避 %.1fs 后重试", attempt + 1, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, BACKOFF_CAP_S)

    async def _consume(self, session_id: str, chat_id: str, key: GroupConversationKey) -> None:
        """常驻读取 Session 事件流：每到一个回合结束(idle)，把该回合最后一条
        agent.message 作为合并回复发到群。断线自动重连，直到会话被 /new 重置。"""
        seen: set[str] = set()
        pending: list[str] = []
        while self._sessions.get(key) == session_id:
            try:
                async with self._ark._open_event_stream(session_id) as stream:  # noqa: SLF001 - 复用客户端流
                    async for event in stream:
                        eid = event.get("id")
                        if eid and eid in seen:
                            continue
                        if eid:
                            seen.add(eid)
                        etype = event.get("type")
                        if etype == "agent.message":
                            body = event_text(event)
                            if body:
                                pending.append(body)
                        elif etype == "session.status_idle":
                            # 一个可调度回合结束：把合并后的最终回复发出去。
                            if pending:
                                await self._send_to_chat(chat_id, pending[-1])
                                pending.clear()
                        elif etype in ("session.error", "session.status_failed"):
                            await self._send_to_chat(chat_id, "本群会话执行出错，请稍后重试或 /new 重置。")
                            pending.clear()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 断线重连
                if self._sessions.get(key) != session_id:
                    break
                log.info("事件流中断，1s 后重连 session=%s", session_id)
                await asyncio.sleep(1.0)

    async def _stop_consumer(self, key: GroupConversationKey) -> None:
        task = self._consumers.pop(key.as_str(), None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def main() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = load_group_bot_config()

    ark = ArkClient(config.ark_api_key, config.ark_base_url)
    sender = FeishuSender(config.feishu_app_id, config.feishu_app_secret)

    loop = asyncio.new_event_loop()
    bot = ConcurrentGroupBot(config, ark, sender, loop)
    threading.Thread(target=loop.run_forever, name="group-bot-loop", daemon=True).start()

    print("Demo C（方舟原生队列）已启动：")
    print(f"- 飞书 App ID：{config.feishu_app_id}")
    print(f"- 群聊共享 Agent ID：{config.ark_agent_id}")
    print("- 策略：消息直发方舟，running 中由服务端队列吸收/合并；不客户端排队。")
    print("在群里让多人几乎同时 @ 这个 bot，观察消息被吸收/合并的效果。指令：/new 重置本群会话。")
    start_feishu_gateway(config.feishu_app_id, config.feishu_app_secret, bot)


if __name__ == "__main__":
    main()
