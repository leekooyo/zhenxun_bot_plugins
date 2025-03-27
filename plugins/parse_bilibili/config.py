from enum import Enum
import os


class BiliContentType(Enum):
    """B站内容类型枚举"""

    CV = "cv"
    OPUS = "opus"
    T_OPUS = "t_opus"


# 链接匹配模式
URL_PATTERNS = {
    "video": r"((?=(?:bv|av))([A-Za-z0-9]+))",
    "b23": r"https://b23\.tv/[A-Za-z0-9]+",
    "other": r"https://(live\.bilibili\.com/\d+|www\.bilibili\.com/read|www\.bilibili\.com/opus|t\.bilibili\.com)/[^?\s]+",
}

# 关键词列表
KEYWORDS: list[str] = [
    "https://live.bilibili.com",
    "https://www.bilibili.com/read/",
    "https://www.bilibili.com/opus/",
    "https://t.bilibili.com/",
]

# 重复解析时间阈值（秒）
REPEAT_THRESHOLD: int = 5

# 消息模板
MESSAGE_TEMPLATES = {
    "video": {
        "format": """av{aid}
标题：{title}
UP：{up_name}
上传日期：{upload_date}
回复：{reply}，收藏：{favorite}，投币：{coin}
点赞：{like}，弹幕：{danmaku}
{url}"""
    },
    "live": {
        "format": """开播用户：https://space.bilibili.com/{uid}
开播时间：{live_time}
直播分区：{parent_area}——>{area}
标题：{title}
简介：{description}
直播截图："""
    },
}

# 截图配置
SCREENSHOT_CONFIG = {
    "VIEWPORT": {"width": 2000, "height": 1000},
    "DEVICE_SCALE_FACTOR": 3,
    "CSS_SELECTORS": {
        BiliContentType.CV: "#app > div > div.article-container",
        BiliContentType.OPUS: "#app > div.opus-detail > div.bili-opus-view",
        BiliContentType.T_OPUS: "#app > div.content > div > div > div.bili-dyn-item__main",
    },
    "CURRENT_DIR": os.path.dirname(os.path.abspath(__file__)),
    "COOKIES_PATH": os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "cookies.json"
    ),
    "TIMEOUT": 60000,  # 页面加载超时时间（毫秒）
}
