from __future__ import annotations

import re
import time
import base64
import random
import string
import hashlib
import urllib.parse
from typing import Any, TypedDict

from httpx import AsyncClient  # type: ignore
import aiohttp
from zhenxun.services.log import logger


class WbiImg(TypedDict):
    img_key: str
    sub_key: str


wbi_img_cache: WbiImg | None = None
dm_img_str_cache: str = base64.b64encode("".join(random.choices(string.printable, k=random.randint(16, 64))).encode())[:-2].decode()  # fmt: skip
dm_cover_img_str_cache: str = base64.b64encode("".join(random.choices(string.printable, k=random.randint(32, 128))).encode())[:-2].decode()  # fmt: skip


async def get_wbi_img(session: aiohttp.ClientSession | AsyncClient, proxy_url: str) -> WbiImg:
    """
    获取 wbi 验证信息
    :param session: aiohttp.ClientSession 或 httpx.AsyncClient
    :param proxy_url: 代理地址
    :return: WbiImg
    """
    global wbi_img_cache
    if wbi_img_cache is not None:
        return wbi_img_cache
        
    url = "https://api.bilibili.com/x/web-interface/nav"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Origin": "https://www.bilibili.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }
    
    try:
        if isinstance(session, aiohttp.ClientSession):
            async with session.get(url, headers=headers, proxy=proxy_url) as response:
                res_json = await response.json()
        else:
            res_json = (await session.get(url, headers=headers, proxy=proxy_url)).json()
            
        assert res_json is not None
        wbi_img: WbiImg = {
            "img_key": _get_key_from_url(res_json["data"]["wbi_img"]["img_url"]),
            "sub_key": _get_key_from_url(res_json["data"]["wbi_img"]["sub_url"]),
        }
        wbi_img_cache = wbi_img
        return wbi_img
        
    except Exception as e:
        logger.warning(f"获取 wbi 验证信息失败: {str(e)[:50]}...")
        raise


def _get_key_from_url(url: str) -> str:
    return url.split("/")[-1].split(".")[0]


def _get_mixin_key(string: str) -> str:
    char_indices = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5,
        49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55,
        40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57,
        62, 11, 36, 20, 34, 44, 52,
    ]  # fmt: skip
    return "".join(list(map(lambda idx: string[idx], char_indices[:32])))


def encode_wbi(params: dict[str, Any], wbi_img: WbiImg):
    img_key = wbi_img["img_key"]
    sub_key = wbi_img["sub_key"]
    illegal_char_remover = re.compile(r"[!'\(\)*]")

    mixin_key = _get_mixin_key(img_key + sub_key)
    time_stamp = int(time.time())
    params_with_wts = dict(params, wts=time_stamp)
    params_with_dm = {
        **params_with_wts,
        "dm_img_list": "[]",
        "dm_img_str": dm_img_str_cache,
        "dm_cover_img_str": dm_cover_img_str_cache,
    }
    url_encoded_params = urllib.parse.urlencode(
        {
            key: illegal_char_remover.sub("", str(params_with_dm[key]))
            for key in sorted(params_with_dm.keys())
        }
    )  # fmt: skip
    w_rid = hashlib.md5((url_encoded_params + mixin_key).encode()).hexdigest()
    all_params = dict(params_with_dm, w_rid=w_rid)
    return all_params
