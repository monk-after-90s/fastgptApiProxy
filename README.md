# fastgptApiProxy

代理fastgpt的agent Api，解决fastgpt的API有时候的数据格式不规范的问题，特别是对接了chatgpt-on-wechat。

## Install

Python 3.12.4

```bash
pip install -r requirements.txt
```

## Run

```bash
OPENAI_BASE_URL={OPENAI_BASE_URL} uvicorn main:app [--workers {worker_num}] [--port {port}]
```

`OPENAI_BASE_URL` is the environment variable for the OpenAI compatible base URL(
end with `/v1`)
of fastgpt server. worker_num is the number of workers, port is the port of the server. worker_num and port are optional.

The API served by this project is compatible with the OpenAI API.

## Citation

```citation
@article{
fastgptApiProxy,
title={fastgptApiProxy: 代理fastgpt的agent Api，解决fastgpt的API有时候的数据格式不规范的问题，特别是对接了chatgpt-on-wechat},
author={monk-after-90s},
journal={},
year={2024}
}
```