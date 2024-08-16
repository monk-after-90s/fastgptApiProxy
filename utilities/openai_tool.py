import os
from typing import AsyncGenerator, Dict
from urllib.parse import urljoin
import httpx
import ujson
from loguru import logger
from urllib.parse import urlparse
from openai import AsyncOpenAI

# 解析出host
parsed_url = urlparse(os.environ['OPENAI_BASE_URL'])
BASE_URL = f"{parsed_url.scheme}://{parsed_url.netloc}"

TIMEOUT = 30


async def modify_openai_response(data: Dict, method: str = "POST", path: str = "",
                                 channel: str = "openai", OPENAI_API_KEY: str = '') \
        -> AsyncGenerator[str, None] | Dict:
    """
    根据是否流式选择处理路线，以及对响应结果的转换

    :param data: 请求体
    """
    if not data.get("stream"):
        async for chat_completion in _request_openai(data, method, path, channel, OPENAI_API_KEY):
            chat_completion = chat_completion.to_dict()
            # 代理fastgpt可能的bug
            if "choices" in chat_completion and \
                    isinstance(chat_completion["choices"][0]['message']['content'], str) and \
                    chat_completion["choices"][0]['message']['content'].startswith("0: "):
                chat_completion["choices"][0]['message']['content'] = \
                    chat_completion["choices"][0]['message']['content'][3:]
            elif "choices" in chat_completion and \
                    isinstance(chat_completion["choices"][0]['message']['content'], list):
                # fastgpt的工具调用返回
                types = set()
                text = ''
                for content in chat_completion["choices"][0]['message']['content']:
                    if isinstance(content, dict):
                        types.add(content.get("type"))
                        if content.get("type") == 'text':
                            text = \
                                content['text']['content'] if not content['text']['content'].startswith("0: ") else \
                                    content['text']['content'][3:]
                if types == {"text", "tool"}:
                    chat_completion["choices"][0]['message']['content'] = text

            return chat_completion
    else:  # todo 实现流式响应
        raise NotImplementedError


async def _request_openai(data: Dict,
                          method: str = "POST",
                          path: str = "",
                          channel: str = "openai",
                          OPENAI_API_KEY: str = '',
                          yield_type: str = "str") -> AsyncGenerator[str, None]:
    """
    对OpenAI API兼容的服务进行请求

    :param data:
    :param method:
    :param path:
    :param channel: 是使用httpx自己构建请求还是openai库。基本上不会使用httpx
    :param yield_type: 流式请求时流数据的类型，默认为str，例如“'data: {"id":"cmpl-c93b280ab24846bcbc5f707ac391a5b6","choices":[{"delta":{"content":"\n"},"finish_reason":null,"index":0,"logprobs":null}],"created":1718868916,"model":"Qwen/Qwen2-72B-Instruct-GPTQ-Int4","object":"chat.completion.chunk"}

'”；或者dict，例如“{"id":"cmpl-c93b280ab24846bcbc5f707ac391a5b6","choices":[{"delta":{"content":"\n"},"finish_reason":null,"index":0,"logprobs":null}],"created":1718868916,"model":"Qwen/Qwen2-72B-Instruct-GPTQ-Int4","object":"chat.completion.chunk"}”
    :return:
    """
    if method != "POST":
        raise NotImplementedError

    if data['messages'][-1].get('role') == 'tool' and 'name' in data['messages'][-1].keys():  # 工具调用结果汇总
        # 清理'assistant'的tool_calls
        for message in data['messages']:
            if message['role'] == 'assistant':
                if 'tool_calls' in message:
                    message.pop('tool_calls')
                if 'content' not in message:
                    message['content'] = '我将调用外部工具回答这个问题...'
        # 清理'tool_choice'
        if 'tool_choice' in data:
            data.pop('tool_choice')
        # 清理'tools'
        if 'tools' in data:
            data.pop('tools')

        # 工具调用结果范围
        tool_res_idxs = []
        meet_tool_res = False
        for i in range(len(data['messages']) - 1, -1, -1):
            if data['messages'][i]['role'] == 'tool':
                meet_tool_res = True
                tool_res_idxs.append(i)
            if meet_tool_res and data['messages'][i]['role'] != 'tool':
                break

        # 工具调用结果转qwen2格式
        tool_res = [data['messages'].pop(i) for i in tool_res_idxs]
        # 应该没有role=tool了
        if any(m['role'] == 'tool' for m in data['messages']):
            raise NotImplementedError
        data['messages'].append({
            'role': 'assistant',
            'content': f"""
        外部工具调用结果：{ujson.dumps(tool_res, ensure_ascii=False)}
                    """,
        })

    if channel == "httpx" and data.get("stream"):
        async with httpx.AsyncClient() as client:
            async with client.stream(
                    method,
                    urljoin(BASE_URL, path),
                    timeout=httpx.Timeout(TIMEOUT),
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                    },
                    json=data,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    c_cache = ''
                    for c in chunk:
                        c_cache += c
                        if c_cache.endswith("\n\n"):
                            logger.debug(f"{c_cache=}")
                            yield c_cache
                            c_cache = ''
                    else:
                        if c_cache:
                            yield c_cache
    elif channel == "openai" and path == "/v1/chat/completions":
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        try:
            logger.info(f"{client.api_key=}")
            if not data.get("stream"):
                yield await client.chat.completions.create(**data)
                return

            stream = await client.chat.completions.create(**data)
            async for chunk in stream:
                if yield_type == "str":
                    chunk_s = "data: " + ujson.dumps(chunk.to_dict(), ensure_ascii=False) + "\n\n"
                    logger.debug(f"{chunk_s=}")
                    yield chunk_s
                elif yield_type == "dict":
                    yield chunk.to_dict()
                else:
                    raise NotImplementedError
        finally:
            await client.close()

    else:
        raise NotImplementedError
