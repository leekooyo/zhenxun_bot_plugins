import time

import ujson as json
from nonebot import on_message
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Hyper, Image, UniMsg
from nonebot_plugin_session import EventSession
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.path_config import TEMP_PATH
from zhenxun.configs.utils import PluginExtraData, RegisterConfig, Task
from zhenxun.services.log import logger
from zhenxun.utils.common_utils import CommonUtils
from zhenxun.utils.enum import PluginType
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.message import MessageUtils

from .config import REPEAT_THRESHOLD
from .information_container import InformationContainer
from .message_handler import MessageHandler
from .parse_url import parse_bili_url
from .url_parser import URLParser

__plugin_meta__ = PluginMetadata(
    name="B站内容解析",
    description="B站内容解析",
    usage="""
    usage：
        被动监听插件，解析B站视频、直播、专栏，支持小程序卡片及文本链接，5分钟内不解析相同内容
    """.strip(),
    extra=PluginExtraData(
        author="leekooyo",
        version="0.1-89d294e",
        plugin_type=PluginType.DEPENDANT,
        menu_type="其他",
        configs=[
            RegisterConfig(
                module="_task",
                key="DEFAULT_BILIBILI_PARSE",
                value=True,
                default_value=True,
                help="被动 B站转发解析 进群默认开关状态",
                type=bool,
            )
        ],
        tasks=[Task(module="bilibili_parse", name="b站转发解析")],
    ).to_dict(),
)


async def _rule(session: Uninfo) -> bool:
    return not await CommonUtils.task_is_block(session, "bilibili_parse")


_matcher = on_message(priority=1, block=False, rule=_rule)

_tmp = {}


@_matcher.handle()
async def _(session: EventSession, message: UniMsg):
    try:
        information_container = InformationContainer()
        message_handler = MessageHandler(session)

        # 获取URL
        get_url = None
        data = message[0]

        # 尝试解析小程序消息
        if isinstance(data, Hyper) and data.raw:
            try:
                data = json.loads(data.raw)
                get_url = URLParser.parse_miniapp(data)
            except (IndexError, KeyError):
                pass

        # 解析文本消息
        if not get_url and (msg := message.extract_plain_text()):
            get_url = URLParser.parse_message(msg)

        if get_url:
            try:
                data = await parse_bili_url(get_url, information_container)

                # 处理不同类型的内容
                if data.vd_info and not message_handler.is_repeat(data.vd_url):
                    await message_handler.handle_video_info(data)
                elif data.live_info and not message_handler.is_repeat(data.live_url):
                    await message_handler.handle_live_info(data)
                elif data.image_info and not message_handler.is_repeat(data.image_url):
                    await message_handler.handle_image_info(data)

            except ValueError as e:
                logger.warning(f"解析B站链接失败: {str(e)}")
                # 静默处理解析失败的情况
                pass

    except Exception as e:
        logger.debug(f"B站解析插件发生错误: {str(e)}")


async def _handle_video_info(data, session):
    """处理视频信息"""
    vd_info = data.vd_info
    pic = vd_info.get("pic", "")
    aid = vd_info.get("aid", "")
    stats = vd_info.get("stat", {})

    logger.info(f"解析bilibili转发 {data.vd_url}", "b站解析", session=session)
    _tmp[data.vd_url] = time.time()

    _path = TEMP_PATH / f"{aid}.jpg"
    await AsyncHttpx.download_file(pic, _path)

    message = [
        _path,
        f"av{aid}\n"
        f"标题：{vd_info.get('title', '')}\n"
        f"UP：{vd_info.get('owner', {}).get('name', '')}\n"
        f"上传日期：{time.strftime('%Y-%m-%d', time.localtime(vd_info['ctime']))}\n"
        f"回复：{stats.get('reply', '')}，收藏：{stats.get('favorite', '')}，投币：{stats.get('coin', '')}\n"
        f"点赞：{stats.get('like', '')}，弹幕：{stats.get('danmaku', '')}\n"
        f"{data.vd_url}",
    ]

    await MessageUtils.build_message(message).send()


async def _handle_live_info(data, session):
    """处理直播信息"""
    live_info = data.live_info
    logger.info(f"解析bilibili转发 {data.live_url}", "b站解析", session=session)
    _tmp[data.live_url] = time.time()

    message = [
        Image(url=live_info.get("user_cover", "")),
        f"开播用户：https://space.bilibili.com/{live_info.get('uid', '')}\n"
        f"开播时间：{live_info.get('live_time', '')}\n"
        f"直播分区：{live_info.get('parent_area_name', '')}——>{live_info.get('area_name', '')}\n"
        f"标题：{live_info.get('title', '')}\n"
        f"简介：{live_info.get('description', '')}\n"
        f"直播截图：\n",
        Image(url=live_info.get("keyframe", "")),
        f"{data.live_url}",
    ]

    await MessageUtils.build_message(message).send()


async def _handle_image_info(data, session):
    """处理图片信息"""
    logger.info(f"解析bilibili转发 {data.image_url}", "b站解析", session=session)
    _tmp[data.image_url] = time.time()
    await data.image_info.send()
