import time
from typing import List, Union

from nonebot_plugin_alconna import Image
from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

from .config import MESSAGE_TEMPLATES
from .information_container import InformationContainer

class MessageHandler:
    def __init__(self, session):
        self.session = session
        self._tmp = {}

    async def handle_video_info(self, data: InformationContainer) -> None:
        """处理视频信息"""
        vd_info = data.vd_info
        pic = vd_info.get("pic", "")
        aid = vd_info.get("aid", "")
        stats = vd_info.get("stat", {})

        logger.info(f"解析bilibili转发 {data.vd_url}", "b站解析", session=self.session)
        self._tmp[data.vd_url] = time.time()

        _path = TEMP_PATH / f"{aid}.jpg"
        await AsyncHttpx.download_file(pic, _path)

        message = [
            _path,
            MESSAGE_TEMPLATES["video"]["format"].format(
                aid=aid,
                title=vd_info.get("title", ""),
                up_name=vd_info.get("owner", {}).get("name", ""),
                upload_date=time.strftime("%Y-%m-%d", time.localtime(vd_info["ctime"])),
                reply=stats.get("reply", ""),
                favorite=stats.get("favorite", ""),
                coin=stats.get("coin", ""),
                like=stats.get("like", ""),
                danmaku=stats.get("danmaku", ""),
                url=data.vd_url
            )
        ]

        await MessageUtils.build_message(message).send()

    async def handle_live_info(self, data: InformationContainer) -> None:
        """处理直播信息"""
        live_info = data.live_info
        logger.info(f"解析bilibili转发 {data.live_url}", "b站解析", session=self.session)
        self._tmp[data.live_url] = time.time()

        message = [
            Image(url=live_info.get("user_cover", "")),
            MESSAGE_TEMPLATES["live"]["format"].format(
                uid=live_info.get("uid", ""),
                live_time=live_info.get("live_time", ""),
                parent_area=live_info.get("parent_area_name", ""),
                area=live_info.get("area_name", ""),
                title=live_info.get("title", ""),
                description=live_info.get("description", "")
            ),
            Image(url=live_info.get("keyframe", "")),
            data.live_url
        ]

        await MessageUtils.build_message(message).send()

    async def handle_image_info(self, data: InformationContainer) -> None:
        """处理图片信息"""
        logger.info(f"解析bilibili转发 {data.image_url}", "b站解析", session=self.session)
        self._tmp[data.image_url] = time.time()
        await data.image_info.send()

    def is_repeat(self, url: str) -> bool:
        """检查是否为重复内容"""
        return url in self._tmp and time.time() - self._tmp[url] <= 5 