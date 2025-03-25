'''
Author: xx
Date: 2025-03-22 15:36:23
LastEditors: Do not edit
LastEditTime: 2025-03-24 22:43:53
Description: 
FilePath: \zhenxun\zhenxun_bot\zhenxun\plugins\parse_bilibili\parse_url.py
'''
import re
from typing import Dict
import aiohttp
import asyncio
from bilireq import live, video
from zhenxun.utils.user_agent import get_user_agent
from .get_image import get_image
from .information_container import InformationContainer

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

def extract_video_id(url: str) -> str:
    """从视频URL中提取视频ID"""
    # 处理 BV号和av号
    if match := re.search(r'/video/(?:av|AV)?([A-Za-z0-9]+)', url, re.IGNORECASE):
        return match.group(1)
    return url.split("/")[-1]

async def parse_bili_url(get_url: str, information_container: InformationContainer) -> Dict:
    """解析 Bilibili 链接，获取相关信息"""
    try:
        # 获取并清理 URL
        url = clean_url(get_url)
        response_url = await get_redirected_url(url)

        # 视频链接处理
        if "/video/" in response_url:
            vid = extract_video_id(response_url)
            try:
                vd_info = await video.get_video_base_info(vid)
                information_container.update({"vd_info": vd_info, "vd_url": response_url})
            except Exception as e:
                raise ValueError(f"获取视频信息失败: {str(e)}")

        # 直播链接处理
        elif "live.bilibili.com" in response_url:
            rid = response_url.split("/")[-1]
            try:
                live_info = await live.get_room_info_by_id(rid)
                information_container.update({"live_info": live_info, "live_url": response_url})
            except Exception as e:
                raise ValueError(f"获取直播间信息失败: {str(e)}")

        # 文章和动态链接处理
        elif any(x in response_url for x in ["/read/", "/opus/", "t.bilibili.com"]):
            try:
                image_info = await get_image(response_url)
                information_container.update({"image_info": image_info, "image_url": response_url})
            except Exception as e:
                raise ValueError(f"获取图片信息失败: {str(e)}")

        else:
            raise ValueError(f"不支持的URL类型: {response_url}")

        return information_container.get_information()

    except Exception as e:
        raise ValueError(f"解析 Bilibili URL 失败: {str(e)}")
