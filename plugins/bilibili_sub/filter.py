import asyncio
import json
import os
from typing import TypedDict

import aiofiles
from playwright._impl._api_structures import SetCookieParam
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from zhenxun.services.log import logger

# 配置常量
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_PATH = os.path.join(CURRENT_DIR, "cookies.json")


class Cookie(TypedDict):
    name: str
    value: str
    domain: str
    path: str
    sameSite: str
    secure: bool
    httpOnly: bool


# 需要检测的广告相关类名
AD_CLASS_NAMES = [
    "opus-text-rich-hl",  # 文字广告
    "goods-shop",  # 商品店铺
    "bili-dyn-card-goods",  # B站动态商品卡片
    "dyn-goods",  # 动态商品
    "dyn-goods__mark",  # 商品标记
]

MAX_ATTEMPTS = 3  # 最大检测重试次数


async def load_cookies() -> list[SetCookieParam] | None:
    """
    加载并处理cookies配置

    Returns:
        List[SetCookieParam] | None: 处理后的cookies列表，失败时返回None
    """
    try:
        async with aiofiles.open(COOKIES_PATH) as f:
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


async def setup_browser_context() -> tuple[Browser, BrowserContext]:
    """
    设置浏览器环境

    Returns:
        tuple[Browser, BrowserContext]: 浏览器实例和上下文
    """
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()

    if cookies := await load_cookies():
        await context.add_cookies(cookies)

    return browser, context


async def check_blocked_elements(page: Page) -> bool:
    """
    检查页面是否包含被拦截的广告元素

    Args:
        page: Playwright页面实例

    Returns:
        bool: True表示发现广告元素，False表示未发现
    """
    for class_name in AD_CLASS_NAMES:
        if await page.locator(f".{class_name}").count() > 0:
            logger.info(f"检测到广告元素: {class_name}")
            return True
    return False


async def check_page_elements(url: str) -> bool:
    """
    检查页面是否包含广告元素

    Args:
        url: 要检查的页面URL

    Returns:
        bool: True表示包含广告，False表示不包含或检查失败
    """
    browser = None
    try:
        browser, context = await setup_browser_context()
        page = await context.new_page()

        for attempt in range(MAX_ATTEMPTS):
            try:
                # 加载页面并等待网络请求完成
                await page.goto(url)
                await page.wait_for_load_state("networkidle")

                # 检查是否包含广告元素
                if await check_blocked_elements(page):
                    return True

                logger.info(f"第{attempt + 1}次检查未发现广告元素，继续检查...")

            except Exception as e:
                msg = f"页面检查过程出错 (尝试 {attempt + 1}/{MAX_ATTEMPTS})"
                logger.error(f"{msg}: {e}")
                continue

        return False

    except Exception as e:
        logger.error(f"广告检查任务失败: {e}")
        return False

    finally:
        if browser:
            await browser.close()


async def main():
    """
    主函数，用于命令行测试
    """
    url = input("请输入要检查的页面URL: ")
    result = await check_page_elements(url)
    print(f"页面广告检测结果: {'包含广告' if result else '未发现广告'}")


if __name__ == "__main__":
    asyncio.run(main())
