import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

import aiofiles
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import get_new_page
from playwright._impl._api_structures import SetCookieParam

from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils.image_utils import BuildImage
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.user_agent import get_user_agent_str


class BiliContentType(Enum):
    """B站内容类型枚举"""
    CV = "cv"
    OPUS = "opus"
    T_OPUS = "t_opus"


@dataclass
class BiliContentInfo:
    """B站内容信息数据类"""
    content_type: BiliContentType
    content_id: str
    url: str


class ScreenshotConfig:
    """截图配置类"""
    VIEWPORT = {"width": 2000, "height": 1000}
    DEVICE_SCALE_FACTOR = 3
    CSS_SELECTORS = {
        BiliContentType.CV: "#app > div > div.article-container",
        BiliContentType.OPUS: "#app > div.opus-detail > div.bili-opus-view",
        BiliContentType.T_OPUS: "#app > div.content > div > div > div.bili-dyn-item__main",
    }
    # 获取当前文件所在目录
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    COOKIES_PATH = os.path.join(CURRENT_DIR, "cookies.json")
    # 页面加载超时时间（毫秒）
    TIMEOUT = 60000


async def load_cookies() -> list[SetCookieParam] | None:
    """加载并处理cookies配置

    Returns:
        List[SetCookieParam] | None: 处理后的cookies列表，失败时返回None
    """
    try:
        async with aiofiles.open(ScreenshotConfig.COOKIES_PATH, "r", encoding="utf-8") as f:
            content = await f.read()
            cookies: list[SetCookieParam] = json.loads(content)

        # 修正cookies的sameSite属性
        for cookie in cookies:
            same_site = cookie.get("sameSite") or ""
            if same_site.lower() == "unspecified":
                cookie["sameSite"] = "Lax"

        return cookies
    except Exception as e:
        logger.error(f"加载cookies失败: {e}")
        return None


async def resize(path: Path) -> None:
    """调整图像大小的异步函数

    Args:
        path: 图像文件路径
    """
    A = BuildImage.open(path)
    await A.resize(0.8)
    await A.save(path)


def parse_bili_url(url: str) -> Optional[BiliContentInfo]:
    """解析B站URL，获取内容类型和ID

    Args:
        url: B站链接

    Returns:
        BiliContentInfo对象，如果无法解析则返回None
    """
    url = url.split("?")[0]
    
    # 定义URL模式
    patterns = {
        BiliContentType.CV: (r"read/cv([A-Za-z0-9]+)", lambda m: m.group(1)),
        BiliContentType.OPUS: (r"opus/([A-Za-z0-9]+)", lambda m: m.group(1)),
        BiliContentType.T_OPUS: (r"https://t\.bilibili\.com/(\d+)", lambda m: m.group(1)),
    }
    
    # 尝试匹配每种类型
    for content_type, (pattern, extractor) in patterns.items():
        if match := re.search(pattern, url, re.IGNORECASE):
            content_id = extractor(match)
            if content_type == BiliContentType.T_OPUS:
                url = f"https://www.bilibili.com/opus/{content_id}"
            return BiliContentInfo(content_type, content_id, url)
    
    return None


async def wait_for_page_load(page) -> bool:
    """等待页面加载完成

    Args:
        page: 页面对象

    Returns:
        bool: 是否加载成功
    """
    try:
        # 等待页面加载完成
        await page.wait_for_load_state("networkidle", timeout=ScreenshotConfig.TIMEOUT)
        # 等待页面DOM加载完成
        await page.wait_for_load_state("domcontentloaded", timeout=ScreenshotConfig.TIMEOUT)
        # 等待页面JavaScript执行完成
        await page.wait_for_load_state("load", timeout=ScreenshotConfig.TIMEOUT)
        return True
    except Exception as e:
        logger.warning(f"页面加载超时: {e}")
        return False


async def get_element_clip(page, css_selector: str, content_type: BiliContentType) -> Optional[dict]:
    """获取元素的边界框信息

    Args:
        page: 页面对象
        css_selector: CSS选择器
        content_type: 内容类型

    Returns:
        dict: 边界框信息，如果获取失败则返回None
    """
    try:
        # 等待页面加载完成
        await page.wait_for_load_state("domcontentloaded")
        
        # 检查404页面
        if page.url == "https://www.bilibili.com/404":
            logger.warning(f"内容不存在: {page.url}")
            return None
            
        # 等待目标元素出现
        element = await page.query_selector(css_selector)
        if not element:
            logger.warning(f"未找到目标元素: {css_selector}")
            return None
            
        # 获取元素边界框
        clip = await element.bounding_box()
        if not clip:
            logger.warning("无法获取元素边界框")
            return None
            
        # 对于动态内容，需要特殊处理
        if content_type == BiliContentType.T_OPUS:
            # 获取底部标签栏
            bar = await page.query_selector(".bili-tabs__header")
            if bar:
                bar_bound = await bar.bounding_box()
                if bar_bound:
                    clip["height"] = bar_bound["y"] - clip["y"]
        
        return clip
        
    except Exception as e:
        logger.warning(f"获取元素边界框失败: {e}")
        return None


async def capture_element_screenshot(
    page,
    css_selector: str,
    screenshot_path: Path,
    content_type: BiliContentType,
) -> bool:
    """捕获指定元素的截图

    Args:
        page: 页面对象
        css_selector: CSS选择器
        screenshot_path: 截图保存路径
        content_type: 内容类型

    Returns:
        bool: 截图是否成功
    """
    try:
        clip = await get_element_clip(page, css_selector, content_type)
        if not clip:
            return False
            
        await page.screenshot(
            path=screenshot_path,
            clip=clip,
            full_page=True,
            type="png",
        )
        return True
    except Exception as e:
        logger.warning(f"截图失败: {e}")
        return False


async def take_screenshot(content_info: BiliContentInfo, screenshot_path: Path) -> bool:
    """执行截图操作

    Args:
        content_info: B站内容信息
        screenshot_path: 截图保存路径

    Returns:
        bool: 截图是否成功
    """
    try:
        cookies = await load_cookies()
        css_selector = ScreenshotConfig.CSS_SELECTORS[content_info.content_type]
        
        async with get_new_page(
            viewport={"width": 2000, "height": 1000},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            device_scale_factor=3,
        ) as page:
            if cookies:
                await page.context.add_cookies(cookies)
            
            await page.goto(content_info.url, wait_until="networkidle")
            
            if not await capture_element_screenshot(page, css_selector, screenshot_path, content_info.content_type):
                return False
                
            await resize(screenshot_path)
            return True
            
    except Exception as e:
        logger.warning(f"截图过程失败: {e}")
        return False


async def get_image(url: str) -> Optional[UniMessage]:
    """获取Bilibili链接的截图，并返回base64格式的图片

    Args:
        url: Bilibili链接

    Returns:
        UniMessage对象，如果获取失败则返回None
    """
    # 解析URL
    content_info = parse_bili_url(url)
    if not content_info:
        logger.warning(f"无法解析URL: {url}")
        return None

    # 构建截图路径
    screenshot_path = TEMP_PATH / f"bilibili_{content_info.content_type.value}_{content_info.content_id}.png"
    
    # 如果文件已存在，直接返回
    if screenshot_path.exists():
        return MessageUtils.build_message(screenshot_path)
    
    # 执行截图
    if not await take_screenshot(content_info, screenshot_path):
        return None
        
    return MessageUtils.build_message(screenshot_path)
