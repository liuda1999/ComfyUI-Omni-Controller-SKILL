"""本地 ComfyUI HTTP 访问工具。

本模块统一使用**无代理**的 urllib opener：本地 ComfyUI 服务（127.0.0.1/局域网）
不应经由环境代理访问。沙箱 / 企业环境常设置 ``HTTP_PROXY``/``HTTPS_PROXY`` 且未设
``NO_PROXY``，会让 ``urllib.request.urlopen`` 把 127.0.0.1 也走代理并返回 502。
"""

from __future__ import annotations

import json as _json
import urllib.request


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def open_url(
    url: str,
    data: bytes | None = None,
    headers: dict | None = None,
    method: str | None = None,
    timeout: float = 15.0,
):
    """以无代理方式发起请求，返回响应对象（可用作 context manager）。"""
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    return _opener().open(req, timeout=timeout)


def get_json(url: str, timeout: float = 15.0):
    with open_url(url, timeout=timeout) as resp:
        return _json.loads(resp.read().decode("utf-8"))
