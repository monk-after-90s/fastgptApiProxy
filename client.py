"""用于开发测试的客户端。需要传入环境变量OPENAI_BASE_URL、OPENAI_API_KEY"""
import asyncio

from openai import AsyncOpenAI

client = AsyncOpenAI()


async def main():
    chat_completion = await client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "你是谁",
            }
        ],
        model=""
    )
    print(chat_completion)


if __name__ == '__main__':
    asyncio.run(main())
