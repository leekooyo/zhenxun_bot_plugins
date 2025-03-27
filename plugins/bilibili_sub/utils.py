import datetime
import random
import traceback
from io import BytesIO
from typing import Any, Dict, List, Optional

import aiohttp
from fake_useragent import UserAgent
from bilireq.user import get_user_info
from nonebot_plugin_htmlrender import get_new_page

from zhenxun.configs.path_config import IMAGE_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.image_utils import BuildImage

from .auth import AuthManager
from .Wbi import encode_wbi, get_wbi_img

class ResponseCodeError(Exception):
    """响应状态码异常"""
    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(f"请求 {url} 失败，状态码: {status_code}")

# 常量配置
BORDER_PATH = IMAGE_PATH / "border"
BORDER_PATH.mkdir(parents=True, exist_ok=True)
BASE_URL = "https://api.bilibili.com"

# 代理配置
PROXY_PORTS = [
    30022, 30073, 30069, 30021, 30026,
    30012, 30004, 30008, 30047, 30024,
    30010, 30043, 30040, 30049, 30046,
    30038, 30013, 30048, 30044, 30041,
    30014, 30029, 30023, 30045, 30039,
    30009, 30025, 30032, 30005, 30011,
    30055, 30027, 30042, 30050, 30053,
    30051, 30061, 30003, 30006, 30030,
    30056, 30031, 30033, 30058, 30054,
    30062, 30028
]

PROXY_LIST = [f"http://127.0.0.1:{port}" for port in PROXY_PORTS]

# HTTP请求通用配置
def get_random_ua() -> str:
    """获取随机User-Agent"""
    ua = UserAgent()
    return ua.random

DEFAULT_HEADERS = {
    "User-Agent": get_random_ua(),
    "Referer": "https://www.bilibili.com",
}

# 添加新的导入
import asyncio
import time
from collections import defaultdict

# 添加IP使用记录和锁
class BiliClient:
    _ip_last_use = defaultdict(float)  # 记录IP最后使用时间
    _ip_locks = {}  # IP锁
    _ip_pool_lock = asyncio.Lock()  # IP池锁
    
    @staticmethod
    def get_random_proxy() -> str:
        """获取随机代理地址"""
        return random.choice(PROXY_LIST)
    
    @classmethod
    async def get_available_proxy(cls) -> str:
        """获取可用的代理地址，确保两次请求间隔至少3秒"""
        async with cls._ip_pool_lock:
            current_time = time.time()
            available_proxies = [
                proxy for proxy in PROXY_LIST
                if current_time - cls._ip_last_use[proxy] >= 3
            ]
            
            if not available_proxies:
                # 等待直到有代理可用
                min_wait_time = min(
                    cls._ip_last_use[proxy] + 3 - current_time 
                    for proxy in PROXY_LIST
                )
                await asyncio.sleep(min_wait_time)
                return await cls.get_available_proxy()
            
            proxy = random.choice(available_proxies)
            cls._ip_last_use[proxy] = current_time
            return proxy

    @staticmethod
    async def get_session() -> aiohttp.ClientSession:
        """获取aiohttp会话"""
        connector = aiohttp.TCPConnector(force_close=True)
        return aiohttp.ClientSession(connector=connector)
    
    @classmethod
    async def request(
        cls,
        url: str,
        params: Optional[Dict] = None,
        timeout: int = 5,
        **kwargs
    ) -> Dict[str, Any]:
        """统一的GET请求处理方法"""
        retry_count = 0
        last_error = None
        
        while retry_count < 5:
            try:
                proxy = await cls.get_available_proxy()
                proxy_url = f"http://{proxy.split('//')[1]}"
                # cookies = {
                #     'bmg_af_switch': '1',
                #     'browser_resolution': '1536-738',
                #     'bmg_src_def_domain': 'i0.hdslb.com',
                #     'enable_web_push': 'DISABLE',
                #     'home_feed_column': '5',
                #     'header_theme_version': 'CLOSE',
                #     'bili_ticket_expires': '1743270526',
                #     'enable_feed_channel': 'ENABLE',
                #     'sid': '8cgsz4er',
                #     'b_nut': '1743011343',
                #     'DedeUserID__ckMd5': 'fb04573a0db13550',
                #     'bili_ticket': 'eyJhbGciOiJIUzI1NiIsImtpZCI6InMwMyIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDMyNzA1ODYsImlhdCI6MTc0MzAxMTMyNiwicGx0IjotMX0.32n0V4uMg5nUIIrXbzZjK9WdmILQkS8X3oWG-HbPCzg',
                #     'b_lsid': '48D1C623_195D393138D',
                #     'buvid_fp': '0d126e68d0a1a41df885d91087eb3db9',
                #     'bili_jct': '03156b96c1c61dec033099d363f8bb40',
                #     'DedeUserID': '280349923',
                #     'SESSDATA': 'c168d57a%2C1758563385%2C23880%2A31CjCG0UbWa-BjnWufuuOItXkg5MdJRLtSnWiIWu2zgzTxrHMWaiEIsLsHAgoMshorUeASVmRUUF81YUJOY2VyWHNISmlyQkRudjQyTU9jbHJkTEhqcGI3cEJoV2pjQWNMMHR2eDZ4THJnM0puZjdZSUt1OHlFREtDX0trNFhjWkNGT3VkUFRWV2dRIIEC',
                #     '_uuid': 'B849534C-A231-DA0E-D71A-0649CE976AD557849infoc',
                #     'buvid4': '693A11F0-E6FA-9C2F-076D-D0DE5641C28143628-025032617-mZFZUp21Bbbm4RdWlK%2FHvg%3D%3D',
                #     'buvid3': '264A3B0B-0CE7-03BF-6CD9-8BEFBF6A656243388infoc'
                # }
                session = await cls.get_session()
                async with session:
                    headers = DEFAULT_HEADERS.copy()
                    headers["User-Agent"] = get_random_ua()  # 每次请求使用新的随机UA
                    async with session.get(
                        url=url,
                        # cookies=cookies,
                        headers=headers,
                        params=params,
                        proxy=proxy_url,
                        timeout=timeout,
                        **kwargs
                    ) as response:
                        if response.status != 200:
                            retry_count += 1
                            last_error = ResponseCodeError(response.status, url)
                            continue
                        return await response.json()
                        
            except Exception as e:
                retry_count += 1
                last_error = e
                
        logger.error(f"请求 {url} 失败，重试5次后仍然失败: {str(last_error)}")
        raise last_error if last_error else ResponseCodeError(500, url)

    @classmethod
    async def get_meta(cls, media_id: int) -> Dict[str, Any]:
        """获取番剧元数据信息"""
        url = f"{BASE_URL}/pgc/review/user"
        try:
            response = await cls.request(url, params={"media_id": media_id})
            return response["data"]
        except ResponseCodeError as e:
            logger.error(f"获取番剧元数据失败: {str(e)}")
            raise

    @classmethod
    async def get_videos(cls, uid: int, timeout: int = 5) -> Dict[str, Any]:
        """获取用户投稿视频信息"""
        url = f"{BASE_URL}/x/space/wbi/arc/search"
        try:
            proxy_url = f"http://{cls.get_random_proxy().split('//')[1]}"
            session = await cls.get_session()
            async with session:
                wbi_img = await get_wbi_img(session, proxy_url=proxy_url)
                params = {
                    "mid": uid,
                    "ps": 30,
                    "tid": 0,
                    "pn": 1,
                    "order": "pubdate",
                }
                params = encode_wbi(params, wbi_img)
                json_date = cls.request(url, params=params, timeout=timeout)
                return await json_date
        except ResponseCodeError as e:
            logger.error(f"获取用户视频列表失败: {str(e)}")
            raise

    @classmethod
    async def get_user_card(cls, mid: int, photo: bool = False) -> Dict[str, Any]:
        """获取用户名片信息"""
        url = f"{BASE_URL}/x/web-interface/card"
        try:
            response = await cls.request(url, params={"mid": mid, "photo": int(photo)})
            return response["data"]["card"]
        except ResponseCodeError as e:
            logger.error(f"获取用户名片失败: {str(e)}")
            raise

    @classmethod
    async def get_user_dynamics(
        cls, 
        uid: int, 
        offset: int = 0, 
        need_top: bool = False
    ) -> Dict[str, Any]:
        """获取用户历史动态"""
        url = "https://api.vc.bilibili.com/dynamic_svr/v1/dynamic_svr/space_history"
        try:
            params = {
                "host_uid": uid,
                "offset_dynamic_id": offset,
                "need_top": int(bool(need_top)),
            }
            return await cls.request(url, params=params)
        except ResponseCodeError as e:
            logger.error(f"获取用户动态失败: {str(e)}")
            raise

    @classmethod
    async def get_room_info(cls, live_id: int) -> Dict[str, Any]:
        """获取直播间信息"""
        url = "https://api.live.bilibili.com/room/v1/Room/get_info"
        try:
            response = await cls.request(url, params={"id": live_id})
            return response["data"]
        except ResponseCodeError as e:
            logger.error(f"获取直播间信息失败: {str(e)}")
            raise

    @classmethod
    async def get_dynamic_screenshot(cls, dynamic_id: int) -> Optional[bytes]:
        """获取动态截图"""
        url = f"https://t.bilibili.com/{dynamic_id}"
        proxy_url = f"http://{cls.get_random_proxy().split('//')[1]}"
        
        try:
            async with get_new_page(
                viewport={"width": 2000, "height": 1000},
                user_agent=DEFAULT_HEADERS["User-Agent"],
                device_scale_factor=3,
                proxy={"server": proxy_url},
            ) as page:
                cookies = AuthManager.get_cookies()
                # cookies = {
                #     'bmg_af_switch': '1',
                #     'browser_resolution': '1536-738',
                #     'bmg_src_def_domain': 'i0.hdslb.com',
                #     'enable_web_push': 'DISABLE',
                #     'home_feed_column': '5',
                #     'header_theme_version': 'CLOSE',
                #     'bili_ticket_expires': '1743270526',
                #     'enable_feed_channel': 'ENABLE',
                #     'sid': '8cgsz4er',
                #     'b_nut': '1743011343',
                #     'DedeUserID__ckMd5': 'fb04573a0db13550',
                #     'bili_ticket': 'eyJhbGciOiJIUzI1NiIsImtpZCI6InMwMyIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDMyNzA1ODYsImlhdCI6MTc0MzAxMTMyNiwicGx0IjotMX0.32n0V4uMg5nUIIrXbzZjK9WdmILQkS8X3oWG-HbPCzg',
                #     'b_lsid': '48D1C623_195D393138D',
                #     'buvid_fp': '0d126e68d0a1a41df885d91087eb3db9',
                #     'bili_jct': '03156b96c1c61dec033099d363f8bb40',
                #     'DedeUserID': '280349923',
                #     'SESSDATA': 'c168d57a%2C1758563385%2C23880%2A31CjCG0UbWa-BjnWufuuOItXkg5MdJRLtSnWiIWu2zgzTxrHMWaiEIsLsHAgoMshorUeASVmRUUF81YUJOY2VyWHNISmlyQkRudjQyTU9jbHJkTEhqcGI3cEJoV2pjQWNMMHR2eDZ4THJnM0puZjdZSUt1OHlFREtDX0trNFhjWkNGT3VkUFRWV2dRIIEC',
                #     '_uuid': 'B849534C-A231-DA0E-D71A-0649CE976AD557849infoc',
                #     'buvid4': '693A11F0-E6FA-9C2F-076D-D0DE5641C28143628-025032617-mZFZUp21Bbbm4RdWlK%2FHvg%3D%3D',
                #     'buvid3': '264A3B0B-0CE7-03BF-6CD9-8BEFBF6A656243388infoc'
                # }
                await page.context.add_cookies([
                    {
                        "domain": ".bilibili.com",
                        "name": name,
                        "path": "/",
                        "value": value,
                    }
                    for name, value in cookies.items()
                ])
                await page.goto(url, wait_until="networkidle")
                
                if page.url == "https://www.bilibili.com/404":
                    logger.warning(f"动态 {dynamic_id} 不存在")
                    return None
                    
                await page.wait_for_load_state(state="domcontentloaded")
                card = await page.query_selector(".card")
                bar = await page.query_selector(".bili-tabs__header")
                
                if not (card and bar):
                    return None
                    
                clip = await card.bounding_box()
                bar_bound = await bar.bounding_box()
                
                if not (clip and bar_bound):
                    return None
                    
                clip["height"] = bar_bound["y"] - clip["y"]
                return await page.screenshot(clip=clip, full_page=True)
                
        except Exception:
            logger.warning(f"Error in get_dynamic_screenshot({url}): {traceback.format_exc()}")
            return None

def format_duration(seconds: float) -> str:
    """格式化时间间隔为人类可读的格式"""
    if seconds < 5:
        return f"{int(seconds * 1000)} 毫秒"
        
    delta = datetime.timedelta(seconds=int(seconds))
    parts = []
    
    if delta.days:
        parts.append(f"{delta.days} 天")
    if delta.seconds // 3600:
        parts.append(f"{delta.seconds // 3600} 小时")
    if (delta.seconds % 3600) // 60:
        parts.append(f"{(delta.seconds % 3600) // 60} 分钟")
    if delta.seconds % 60 and not parts:
        parts.append(f"{delta.seconds % 60} 秒")
        
    return " ".join(parts)
