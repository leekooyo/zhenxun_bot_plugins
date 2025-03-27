import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiofiles
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import get_new_page
from playwright._impl._api_structures import SetCookieParam

from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils.image_utils import BuildImage
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.user_agent import get_user_agent_str

from .config import BiliContentType, SCREENSHOT_CONFIG


@dataclass
class BiliContentInfo:
    """B站内容信息数据类"""
    content_type: BiliContentType
    content_id: str
    url: str


async def load_cookies() -> list[SetCookieParam] | None:
    """加载并处理cookies配置"""
    try:
        async with aiofiles.open(SCREENSHOT_CONFIG["COOKIES_PATH"], "r", encoding="utf-8") as f:
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
    """调整图像大小的异步函数"""
    A = BuildImage.open(path)
    await A.resize(0.8)
    await A.save(path)


def parse_bili_url(url: str) -> Optional[BiliContentInfo]:
    """解析B站URL，获取内容类型和ID"""
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
    """等待页面加载完成"""
    try:
        await page.wait_for_load_state("networkidle", timeout=SCREENSHOT_CONFIG["TIMEOUT"])
        await page.wait_for_load_state("domcontentloaded", timeout=SCREENSHOT_CONFIG["TIMEOUT"])
        await page.wait_for_load_state("load", timeout=SCREENSHOT_CONFIG["TIMEOUT"])
        return True
    except Exception as e:
        logger.warning(f"页面加载超时: {e}")
        return False


async def get_element_clip(page, css_selector: str, content_type: BiliContentType) -> Optional[dict]:
    """获取元素的边界框信息"""
    try:
        await page.wait_for_load_state("domcontentloaded")

        if page.url == "https://www.bilibili.com/404":
            logger.warning(f"内容不存在: {page.url}")
            return None

        element = await page.query_selector(css_selector)
        if not element:
            logger.warning(f"未找到目标元素: {css_selector}")
            return None

        clip = await element.bounding_box()
        if not clip:
            logger.warning("无法获取元素边界框")
            return None

        if content_type == BiliContentType.T_OPUS:
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
    """捕获指定元素的截图"""
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
    """执行截图操作"""
    try:
        cookies = await load_cookies()
        css_selector = SCREENSHOT_CONFIG["CSS_SELECTORS"][content_info.content_type]

        async with get_new_page(
            viewport=SCREENSHOT_CONFIG["VIEWPORT"],
            user_agent=get_user_agent_str(),
            device_scale_factor=SCREENSHOT_CONFIG["DEVICE_SCALE_FACTOR"],
        ) as page:
            if cookies:
                await page.context.add_cookies(cookies)

            await page.goto(content_info.url)
            if not await wait_for_page_load(page):
                return False

            if await capture_element_screenshot(page, css_selector, screenshot_path, content_info.content_type):
                await resize(screenshot_path)
                return True

        return False
    except Exception as e:
        logger.warning(f"截图过程发生错误: {e}")
        return False


async def get_image(url: str) -> Optional[UniMessage]:
    """获取B站内容的截图"""
    try:
        content_info = parse_bili_url(url)
        if not content_info:
            return None

        screenshot_path = TEMP_PATH / f"{content_info.content_type.value}_{content_info.content_id}.png"
        if await take_screenshot(content_info, screenshot_path):
            return MessageUtils.build_message([screenshot_path])
        return None
    except Exception as e:
        logger.warning(f"获取图片失败: {e}")
        return None
