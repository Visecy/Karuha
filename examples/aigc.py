from argparse import Namespace
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple

import greenback
from openai import APIError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic_core import to_json

import karuha
from karuha import CommandSession, on_command, on_rule
from karuha.command.collection import get_collection
from karuha.data.data import get_data
from karuha.store import MessageBoundDataModel, get_store
from karuha.text.message import Head, Message, MessageSession
from karuha.utils.argparse import ArgumentParser


class AigcResponseInfo(MessageBoundDataModel):
    end_seq_id: int


aigc_resp_store = get_store("json", "aigc_response_info", data_type=AigcResponseInfo, indent=4)
_aigc_cache: Dict[Tuple[str, int], Tuple[Optional[int], str, Any]] = {}


async def parse_aigc_user_text(session: MessageSession, topic: str, message: Message) -> Tuple[Optional[int], str, Namespace]:
    aigc_parser = ArgumentParser(session, "aigc", description="Large language model interface commands. Use the reply function to add context to them.")
    aigc_parser.add_argument("-m", "--model", type=str, help="指定用于对话的模型名称")
    aigc_parser.add_argument("-t", "--temperature", type=float, default=0.85)
    aigc_parser.add_argument("-s", "--seed", type=int, default=1234)
    aigc_parser.add_argument("-S", "--system-prompt")
    aigc_parser.add_argument("-w", "--web-search", action="store_true")
    aigc_parser.add_argument("message", type=str, nargs='+')

    argv = message.text.split(' ')
    ns = aigc_parser.parse_args([str(i) for i in argv[1:]])
    await aigc_parser.wait_tasks()
    
    reply = message.head.get("reply")
    reply = reply and int(reply)
    quote = message.quote
    if quote and reply and quote.mention:
        if quote.mention.val != session.bot.uid:
            await session.finish("invalid chat context")
        if quote.quote_content and (topic, reply) not in _aigc_cache:
            _aigc_cache[topic, reply] = None, str(quote.quote_content), None
    prompt = ' '.join(ns.message)
    _aigc_cache[topic, message.seq_id] = reply, prompt, ns
    session.bot.logger.debug(f"aigc usr traceback {message.seq_id} => {reply}")
    return reply, prompt, ns


async def get_aigc_usr_text(session: MessageSession, topic: str, usr_seq: int) -> Tuple[Optional[int], str, Optional[Namespace]]:
    if user_text_info := _aigc_cache.get((topic, usr_seq)):
        return user_text_info
    message = await session.get_data(seq_id=usr_seq)
    session.bot.logger.debug(f"aigc usr context text: {message.text!r} ({message.head})")

    collection = get_collection()
    if collection.name_parser.precheck(message):
        return await parse_aigc_user_text(session, topic, message)
    reply = int(message.head["reply"])
    _aigc_cache[topic, message.seq_id] = reply, message.plain_text, None
    return reply, message.plain_text, None


async def get_aigc_ast_text(session: MessageSession, topic: str, ast_seq: int, *, silent: bool = False) -> Tuple[int, str, int]:
    ast_text_info = _aigc_cache.get((topic, ast_seq))
    if ast_text_info is None:
        user_seq = text = turn = None
    else:
        user_seq, text, turn = ast_text_info
    if text is None or turn is None:
        message = await session.get_data(seq_id=ast_seq)
        if ast_resp_info := aigc_resp_store.get((topic, ast_seq)):
            ast_final_seq = ast_resp_info.end_seq_id
            final_message = await get_data(session.bot, topic, seq_id=ast_final_seq)
            text = final_message.plain_text
        elif text is None:
            if silent:
                session.cancel()
            await session.finish("The conversation has expired, please restart the conversation")
        session.bot.logger.debug(f"aigc ast context text: {text!r} ({message.head})")
        user_seq = message.head.get("aigc_reply")
        turn = message.head.get("aigc_turn", 0)
        _aigc_cache[topic, ast_seq] = user_seq, text, turn
    
    if turn >= 10:
        await session.finish("The maximum number of conversation rounds has been reached. Please restart the conversation")
    if user_seq is None:
        await session.finish("invalid chat context")
    return user_seq, text, turn


openai_client = AsyncOpenAI()


async def aigc_call(session: MessageSession, messages: List[ChatCompletionMessageParam], ns: Namespace, turn: int, reply_user_seq: int) -> None:
    session.bot.logger.info(f"aigc message: {to_json(messages, indent=4)}")
    text_seq = await session.send("...", head={"aigc_turn": turn + 1, "aigc_reply": reply_user_seq})
    assert isinstance(text_seq, int)

    buf = StringIO()
    try:
        stream = await openai_client.chat.completions.create(
            model=ns.model,
            messages=messages,
            stream=True,
            temperature=ns.temperature,
            seed=ns.seed,
            extra_body={"enable_search": ns.web_search}
        )
        async for chunk in stream:
            if content := chunk.choices[0].delta.content:
                buf.write(content)
                final_seq = await session.send(buf.getvalue(), replace=text_seq)
    except APIError as e:
        await session.send(str(e), replace=text_seq)
        return
    except Exception:
        await session.send("Generation failed", replace=text_seq)
        raise
    assert final_seq is not None
    topic = session.topic
    aigc_resp_store.add(AigcResponseInfo(topic=topic, seq_id=text_seq, end_seq_id=final_seq))
    _aigc_cache[topic, text_seq] = reply_user_seq, buf.getvalue(), turn + 1


@on_command()
async def aigc(session: CommandSession, topic: str, seq_id: int, message: Message) -> None:
    await greenback.ensure_portal()
    ast_before, usr_text, ns = await parse_aigc_user_text(session, topic, message)
    messages: List[ChatCompletionMessageParam] = [{"role": "user", "content": usr_text}]
    turn = 0
    while ast_before is not None:
        usr_before, ast_text, ast_turn = await get_aigc_ast_text(session, topic, ast_before)
        turn = max(turn, ast_turn)
        messages.append({"role": "assistant", "content": ast_text})
        ast_before, usr_text, usr_ns = await get_aigc_usr_text(session, topic, usr_before)
        messages.append({"role": "user", "content": usr_text})
        if usr_ns is not None:
            vars(usr_ns).update(vars(ns))
            ns = usr_ns
    if ns.system_prompt:
        messages.append({"role": "system", "content": ns.system_prompt})
    messages = list(reversed(messages))
    await aigc_call(session, messages, ns, turn, seq_id)


@on_rule(quote=True, to_me=True, weights=0.6)
async def aigc_from_quote(session: MessageSession, topic: str, text: str, seq_id: int, reply: Head[int]) -> None:
    await greenback.ensure_portal()
    session.bot.logger.debug(f"aigc quote: {reply}")
    messages: List[ChatCompletionMessageParam] = [{"role": "user", "content": text}]
    turn = 0
    ast_before = reply
    ns = None
    while ast_before is not None:
        usr_before, ast_text, ast_turn = await get_aigc_ast_text(session, topic, ast_before, silent=True)
        turn = max(turn, ast_turn)
        messages.append({"role": "assistant", "content": ast_text})
        ast_before, usr_text, usr_ns = await get_aigc_usr_text(session, topic, usr_before)
        messages.append({"role": "user", "content": usr_text})
        if usr_ns is not None:
            if ns is not None:
                vars(usr_ns).update(vars(ns))
            ns = usr_ns

    assert ns is not None
    if ns.system_prompt:
        messages.append({"role": "system", "content": ns.system_prompt})
    messages = list(reversed(messages))
    await aigc_call(session, messages, ns, turn, seq_id)


if __name__ == "__main__":
    karuha.load_config()
    karuha.run()