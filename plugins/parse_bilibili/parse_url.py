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
    # 移除URL参数和末尾斜杠
    url = url.split("?")[0].rstrip("/")
    # 确保URL格式正确
    if "live.bilibili.com" in url:
        # 确保直播URL格式为 https://live.bilibili.com/房间号
        match = re.search(r"live\.bilibili\.com/(\d+)", url)
        if match:
            return f"https://live.bilibili.com/{match.group(1)}"
    return url


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
    if match := re.search(r"/video/(?:av|AV)?([A-Za-z0-9]+)", url, re.IGNORECASE):
        return match.group(1)
    return url.split("/")[-1]


def extract_live_id(url: str) -> str:
    """从直播URL中提取房间号"""
    if match := re.search(r"live\.bilibili\.com/(\d+)", url):
        return match.group(1)
    return url.split("/")[-1]


async def parse_video(url: str, information_container: InformationContainer) -> None:
    """解析视频信息"""
    vid = extract_video_id(url)
    try:
        vd_info = await video.get_video_base_info(vid)
        information_container.update({"vd_info": vd_info, "vd_url": url})
    except Exception as e:
        raise ValueError(f"获取视频信息失败: {str(e)}")


async def parse_live(url: str, information_container: InformationContainer) -> None:
    """解析直播信息"""
    rid = extract_live_id(url)
    try:
        live_info = await live.get_room_info_by_id(rid)
        information_container.update({"live_info": live_info, "live_url": url})
    except Exception as e:
        raise ValueError(f"获取直播间信息失败: {str(e)}")


async def parse_article(url: str, information_container: InformationContainer) -> None:
    """解析文章和动态信息"""
    try:
        image_info = await get_image(url)
        information_container.update({"image_info": image_info, "image_url": url})
    except Exception as e:
        raise ValueError(f"获取图片信息失败: {str(e)}")


async def parse_bili_url(
    get_url: str, information_container: InformationContainer
) -> Dict:
    """解析 Bilibili 链接，获取相关信息"""
    try:
        # 获取并清理 URL
        url = clean_url(get_url)
        response_url = await get_redirected_url(url)

        # 根据URL类型进行解析
        if "/video/" in response_url:
            await parse_video(response_url, information_container)
        elif "live.bilibili.com" in response_url:
            await parse_live(response_url, information_container)
        elif any(x in response_url for x in ["/read/", "/opus/", "t.bilibili.com"]):
            await parse_article(response_url, information_container)
        else:
            raise ValueError(f"不支持的URL类型: {response_url}")

        return information_container.get_information()

    except Exception as e:
        raise ValueError(f"解析 Bilibili URL 失败: {str(e)}")
