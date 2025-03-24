from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import Config
from zhenxun.configs.utils import BaseBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils

from .data_source import update_setu_img

import asyncio
from asyncio import timeout

__plugin_meta__ = PluginMetadata(
    name="更新色图",
    description="更新数据库内存在的色图",
    usage="""
    更新数据库内存在的色图
    指令：
        更新色图
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.1",
        plugin_type=PluginType.SUPERUSER,
        limits=[BaseBlock(result="色图正在更新...")],
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna("更新色图"), rule=to_me(), permission=SUPERUSER, priority=1, block=True
)

# 添加信号量控制
_update_setu_semaphore = asyncio.Semaphore(5)

@_matcher.handle()
async def handle_update_setu_command(session: EventSession, arparma: Arparma):
    if not Config.get_config("send_setu", "DOWNLOAD_SETU"):
        await MessageUtils.build_message("更新色图配置未开启...").send()
        return
        
    await MessageUtils.build_message("开始更新色图...").send(reply_to=True)
    result = await update_setu_img(True)
    if result:
        await MessageUtils.build_message(result).send()
    logger.info("更新色图", arparma.header_result, session=session)


# 更新色图
@scheduler.scheduled_job(
    "cron",
    hour=4,
    minute=30,
)
async def update_setu_images_task():
    if not Config.get_config("send_setu", "DOWNLOAD_SETU"):
        return
        
    try:
        async with _update_setu_semaphore:
            async with timeout(600):
                result = await update_setu_img()
                if result:
                    logger.info(result, "自动更新色图")
    except asyncio.TimeoutError:
        logger.error("更新色图任务超时...")
    except Exception as e:
        logger.error("更新色图任务失败", e=e)
