from datetime import datetime
from pathlib import Path
import shutil
import asyncio
from asyncio import timeout
from dataclasses import dataclass
from typing import Optional

import nonebot
from nonebot.adapters import Bot
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_session import EventSession
from playwright.async_api import TimeoutError

from zhenxun.configs.path_config import TEMPLATE_PATH
from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig, Task
from zhenxun.services.log import logger
from zhenxun.services.plugin_init import PluginInit
from zhenxun.utils.common_utils import CommonUtils
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import broadcast_group
from zhenxun.utils.platform import PlatformUtils
from zhenxun.models.group_console import GroupConsole

from .config import REPORT_PATH
from .data_source import Report

__plugin_meta__ = PluginMetadata(
    name="真寻日报",
    description="嗨嗨，这里是小记者真寻哦",
    usage="""
    指令：
        真寻日报
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.3",
        superuser_help="""重置真寻日报""",
        commands=[Command(command="真寻日报")],
        tasks=[Task(module="mahiro_report", name="真寻日报")],
        configs=[  # 添加配置项提示用户如何获取和填写ALAPI_TOKEN
            RegisterConfig(
                module="alapi",
                key="ALAPI_TOKEN",
                value=None,
                help="在https://admin.alapi.cn/user/login登录后获取token",
            ),
            RegisterConfig(
                key="FULL_SHOW",
                value=False,
                help="完全显示it资讯和60s",
                default_value=False,
                type=bool,
            ),
        ],
    ).to_dict(),
)


RESOURCE_PATH = TEMPLATE_PATH / "mahiro_report"

_matcher = on_alconna(Alconna("真寻日报"), priority=5, block=True, use_origin=True)

_reset_matcher = on_alconna(
    Alconna("重置真寻日报"), priority=5, block=True, permission=SUPERUSER
)


@_reset_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    file = REPORT_PATH / f"{datetime.now().date()}.png"
    if file.exists():
        file.unlink()
        logger.info("重置真寻日报", arparma.header_result, session=session)
    await MessageUtils.build_message("真寻日报已重置!").send()


@_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    try:
        await MessageUtils.build_message(await Report.get_report_image()).send()
        logger.info("查看真寻日报", arparma.header_result, session=session)
    except TimeoutError:
        await MessageUtils.build_message("真寻日报生成超时...").send(at_sender=True)
        logger.error("真寻日报生成超时", arparma.header_result, session=session)


class MyPluginInit(PluginInit):
    async def install(self):
        res = Path(__file__).parent / "mahiro_report"
        if res.exists():
            if RESOURCE_PATH.exists():
                shutil.rmtree(RESOURCE_PATH)
            shutil.move(res, RESOURCE_PATH)
            logger.info(f"移动 真寻日报 资源文件夹成功 {res} -> {RESOURCE_PATH}")

    async def remove(self):
        if RESOURCE_PATH.exists():
            shutil.rmtree(RESOURCE_PATH)
            logger.info(f"删除 真寻日报 资源文件夹成功 {RESOURCE_PATH}")


driver = nonebot.get_driver()


async def check(bot: Bot, group_id: str) -> bool:
    return not await CommonUtils.task_is_block(bot, "mahiro_report", group_id)


@dataclass
class BroadcastResult:
    """广播结果"""
    success: bool
    message: str

class GroupManager:
    """群组管理类"""
    @staticmethod
    async def get_platform_groups(platform: str) -> list[str]:
        """获取指定平台的有效群组"""
        return await GroupConsole.filter(
            status=True,
            channel_id__isnull=True,
            platform=platform
        ).values_list("group_id", flat=True)

class ReportGenerator:
    """报告生成器"""
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.cache_dir = REPORT_PATH  # 使用已定义的报告缓存路径

    def _get_today_cache(self) -> Optional[Path]:
        """获取今日缓存文件"""
        today = datetime.now().date()
        cache_file = self.cache_dir / f"{today}.png"
        return cache_file if cache_file.exists() else None

    async def _generate_new_report(self) -> Optional[Path]:
        """生成新报告"""
        try:
            return await asyncio.wait_for(
                Report.get_report_image(),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            logger.error("生成日报超时")
            return None
        except Exception as e:
            logger.error(f"生成日报失败: {e}")
            return None

    async def get_report(self) -> Optional[Path]:
        """获取报告，优先使用缓存"""
        # 检查缓存
        if cache_file := self._get_today_cache():
            logger.info("使用缓存的日报文件")
            return cache_file
        
        # 生成新报告
        logger.info("开始生成新的日报文件")
        return await self._generate_new_report()

class MessageSender:
    """消息发送器"""
    def __init__(self, interval: int = 60):
        self.interval = interval
        
    async def send_to_group(self, bot: Bot, group_id: str, message) -> BroadcastResult:
        """发送消息到单个群组"""
        try:
            if not await check(bot, group_id):
                return BroadcastResult(False, f"群 {group_id} 已禁用日报功能")
                
            await PlatformUtils.send_message(bot, None, group_id, message)
            return BroadcastResult(True, f"向群 {group_id} 发送成功")
        except Exception as e:
            return BroadcastResult(False, f"向群 {group_id} 发送失败: {e}")

    async def send_sequential(self, bot: Bot, groups: list[str], message) -> list[BroadcastResult]:
        """顺序发送消息到多个群组"""
        results = []
        for group_id in groups:
            result = await self.send_to_group(bot, group_id, message)
            results.append(result)
            if result.success:
                await asyncio.sleep(self.interval)
        return results

class DailyReportService:
    """日报服务"""
    def __init__(self):
        self.generator = ReportGenerator()
        self.sender = MessageSender()
        self._semaphore = asyncio.Semaphore(5)

    async def _get_bots(self) -> dict[str, Bot]:
        """获取可用的机器人"""
        bots = nonebot.get_bots()
        if not bots:
            logger.error("没有可用的Bot连接")
        return bots

    async def broadcast(self) -> bool:
        """执行广播任务"""
        async with self._semaphore:
            # 获取报告（优先使用缓存）
            report_file = await self.generator.get_report()
            if not report_file:
                logger.error("无法获取日报文件")
                return False

            # 获取机器人列表
            bots = await self._get_bots()
            if not bots:
                return False

            message = MessageUtils.build_message(report_file)
            
            # 按平台发送
            for bot in bots.values():
                platform = PlatformUtils.get_platform(bot)
                groups = await GroupManager.get_platform_groups(platform)
                
                if not groups:
                    logger.info(f"平台 {platform} 没有需要发送的群组")
                    continue

                results = await self.sender.send_sequential(bot, groups, message)
                
                # 记录发送结果
                success_count = sum(1 for r in results if r.success)
                fail_count = len(results) - success_count
                logger.info(f"平台 {platform} 发送完成: 成功 {success_count}, 失败 {fail_count}")
                
                # 记录详细失败信息
                for result in results:
                    if not result.success:
                        logger.error(result.message)

            return True

# 创建服务实例
daily_report = DailyReportService()

@scheduler.scheduled_job(
    "cron",
    hour=9,
    minute=0,
)
async def broadcast_daily_report_task():
    """定时广播日报任务"""
    start_time = datetime.now()
    success = await daily_report.broadcast()
    elapsed = (datetime.now() - start_time).total_seconds()
    
    if success:
        logger.info(f"日报广播任务完成，耗时: {elapsed:.2f}秒")
    else:
        logger.error(f"日报广播任务失败，耗时: {elapsed:.2f}秒")

# 添加提前生成缓存的任务
@scheduler.scheduled_job(
    "cron",
    hour=8,  # 提前一小时生成
    minute=30,
)
async def prepare_daily_report():
    """提前生成日报缓存"""
    try:
        report_file = await daily_report.generator._generate_new_report()
        if report_file:
            logger.info("日报缓存文件生成成功")
        else:
            logger.error("日报缓存文件生成失败")
    except Exception as e:
        logger.error(f"生成日报缓存时发生错误: {e}")
