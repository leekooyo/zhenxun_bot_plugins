import re
from typing import Optional, Tuple

from .config import URL_PATTERNS, KEYWORDS


class URLParser:
    @staticmethod
    def parse_message(msg: str) -> Optional[str]:
        """
        解析消息中的URL
        返回: URL或None
        """
        # 检查b23链接
        if "b23.tv" in msg:
            match = re.search(URL_PATTERNS["b23"], msg, re.IGNORECASE)
            if match:
                return match.group()

        # 检查视频号
        elif "bv" in msg.lower() or "av" in msg.lower():
            match = re.search(URL_PATTERNS["video"], msg, re.IGNORECASE)
            if match:
                number = match.group(1)
                return f"https://www.bilibili.com/video/{number}"

        # 检查其他链接
        elif any(keyword in msg for keyword in KEYWORDS):
            # 对于直播链接，使用更精确的匹配模式
            if "live.bilibili.com" in msg:
                match = re.search(r"https://live\.bilibili\.com/\d+", msg)
            else:
                match = re.search(URL_PATTERNS["other"], msg)
            if match:
                return match.group()

        return None

    @staticmethod
    def parse_miniapp(data: dict) -> Optional[str]:
        """
        解析小程序消息中的URL
        """
        if data.get("app") == "com.tencent.qun.invite":
            return None

        meta_data = data.get("meta", {})
        news_value = meta_data.get("news", {})
        detail_1_value = meta_data.get("detail_1", {})
        qqdocurl_value = detail_1_value.get("qqdocurl", {})
        jumpUrl_value = news_value.get("jumpUrl", {})

        url = qqdocurl_value if qqdocurl_value else jumpUrl_value
        if url:
            return url.split("?")[0]
        return None
