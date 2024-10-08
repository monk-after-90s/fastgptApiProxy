import os
import ujson
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response
import httpx
from loguru import logger
from urllib.parse import urlparse
from fastapi.middleware.cors import CORSMiddleware
from utilities.openai_tool import modify_openai_response

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有HTTP头
)
# OPENAI_BASE_URL校验
if not os.environ['OPENAI_BASE_URL'].endswith("/v1"):
    raise ValueError("OPENAI_BASE_URL must end with /v1")
TARGET_BASE_URL = os.environ['OPENAI_BASE_URL'][:-3]
# 全局唯一的 httpx.AsyncClient 实例
client: None | httpx.AsyncClient = None


@app.on_event("startup")
async def startup_event():
    global client
    client = httpx.AsyncClient()
    logger.info("HTTP client initialized")


@app.on_event("shutdown")
async def shutdown_event():
    global client
    await client.aclose()
    logger.info("HTTP client closed")


@app.middleware("http")
async def proxy_middleware(request: Request, call_next):
    # 构建目标URL
    url = f"{TARGET_BASE_URL}{request.url.path}"
    logger.debug(f"target url: {url}")
    # 获取请求方法
    method = request.method

    # 获取请求头
    headers = dict(request.headers)
    parsed_url = urlparse(url)
    host = parsed_url.netloc
    headers["host"] = headers["x-forwarded-host"] = host
    # 获取OPENAI_API_KEY
    assert 'authorization' in headers and headers['authorization'].startswith("Bearer ")
    OPENAI_API_KEY = headers['authorization'].split(' ')[1]
    if method == "POST" and "/v1/chat/completions" == request.url.path:
        data = await request.json()
        logger.debug(f"{data=}")

        stream_gen = await modify_openai_response(data=data, path=request.url.path,
                                                  channel="openai", OPENAI_API_KEY=OPENAI_API_KEY)

        if data.get("stream", False):
            resp = StreamingResponse(stream_gen, media_type="text/event-stream")
        else:
            resp = Response(ujson.dumps(stream_gen, ensure_ascii=False), status_code=200,
                            headers={"content-Type": "application/json"})

        resp.headers["Access-Control-Allow-Origin"] = "*"

        return resp
    elif ((await request.body()) and (await request.json()).get("stream")) or request.query_params.get("stream"):
        # 通用流式处理，应该基本没啥用
        data = await request.json()
        logger.debug(f"{data=}")

        resp = StreamingResponse(
            modify_openai_response(data=data, method=method, path=request.url.path, channel="httpx",
                                   OPENAI_API_KEY=OPENAI_API_KEY),
            media_type="text/event-stream")
        resp.headers["Access-Control-Allow-Origin"] = "*"

        return resp
    else:
        # 其他非流式请求
        # 获取请求体
        body = await request.body()
        # 发送请求到目标服务
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            content=body,
            params=request.query_params
        )

        # 构建响应
        return Response(await response.aread(), status_code=response.status_code, headers=response.headers)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
