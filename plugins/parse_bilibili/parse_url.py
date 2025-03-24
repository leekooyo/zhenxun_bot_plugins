'''
Author: xx
Date: 2025-03-22 15:36:23
LastEditors: Do not edit
LastEditTime: 2025-03-24 16:05:28
Description: 
FilePath: \zhenxun\zhenxun_bot\zhenxun\plugins\parse_bilibili\parse_url.py
'''
from typing import Dict, Callable, Coroutine, Any
import aiohttp
import asyncio
from bilireq import live, video
from zhenxun.utils.user_agent import get_user_agent
from .get_image import get_image
from .information_container import InformationContainer

# URL 处理器映射
URL_HANDLERS = {
    "www.bilibili.com/video": lambda vid, url: video.get_video_base_info(vid),
    "m.bilibili.com/video": lambda vid, url: video.get_video_base_info(vid),
    "live.bilibili.com": lambda rid, url: live.get_room_info_by_id(rid),
    "www.bilibili.com/read": lambda _, url: get_image(url),
    "www.bilibili.com/opus": lambda _, url: get_image(url),
    "t.bilibili.com": lambda _, url: get_image(url),
}

def clean_url(url: str) -> str:
    """清理和标准化 URL"""
    return url.rstrip("/").split("?")[0]

async def get_redirected_url(url: str) -> str:
    """获取重定向后的 URL"""
    async with aiohttp.ClientSession(headers=get_user_agent()) as session:
        try:
            async with session.get(url, timeout=7) as response:
                return clean_url(str(response.url))
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise ValueError(f"获取 URL 失败: {e}")

async def parse_bili_url(get_url: str, information_container: InformationContainer) -> Dict:
    """解析 Bilibili 链接，获取相关信息"""
    try:
        # 获取并清理 URL
        url = clean_url(get_url)
        response_url = await get_redirected_url(url)

        # 查找匹配的处理器
        handler = None
        for url_pattern, url_handler in URL_HANDLERS.items():
            if url_pattern in response_url:
                handler = url_handler
                break
        
        if not handler:
            raise ValueError(f"不支持的 URL 类型: {response_url}")

        # 提取 ID 并处理
        resource_id = response_url.split("/")[-1]
        info = await handler(resource_id, response_url)

        # 更新信息容器
        if "video" in response_url:
            information_container.update({"vd_info": info, "vd_url": response_url})
        elif "live" in response_url:
            information_container.update({"live_info": info, "live_url": response_url})
        else:
            information_container.update({"image_info": info, "image_url": response_url})

        return information_container.get_information()

    except Exception as e:
        raise ValueError(f"解析 Bilibili URL 失败: {e}")
