from datetime import datetime
from pathlib import Path
import shutil
import asyncio
from typing import Dict, List, Optional

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
        configs=[
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

class ReportCommand:
    """日报命令处理器"""
    def __init__(self):
        self.matcher = on_alconna(Alconna("真寻日报"), priority=5, block=True, use_origin=True)
        self.reset_matcher = on_alconna(
            Alconna("重置真寻日报"), priority=5, block=True, permission=SUPERUSER
        )
        self._register_handlers()

    def _register_handlers(self):
        """注册命令处理器"""
        @self.reset_matcher.handle()
        async def reset_handler(session: EventSession, arparma: Arparma):
            await self._handle_reset(session, arparma)

        @self.matcher.handle()
        async def report_handler(session: EventSession, arparma: Arparma):
            await self._handle_report(session, arparma)

    async def _handle_reset(self, session: EventSession, arparma: Arparma):
        """处理重置命令"""
        file = REPORT_PATH / f"{datetime.now().date()}.png"
        if file.exists():
            file.unlink()
            logger.info("重置真寻日报", arparma.header_result, session=session)
        await MessageUtils.build_message("真寻日报已重置!").send()

    async def _handle_report(self, session: EventSession, arparma: Arparma):
        """处理日报命令"""
        try:
            await MessageUtils.build_message(await Report.get_report_image()).send()
            logger.info("查看真寻日报", arparma.header_result, session=session)
        except TimeoutError:
            await MessageUtils.build_message("真寻日报生成超时...").send(at_sender=True)
            logger.error("真寻日报生成超时", arparma.header_result, session=session)

class ResourceManager:
    """资源管理器"""
    def __init__(self):
        self.resource_path = RESOURCE_PATH

    async def install(self):
        """安装资源"""
        res = Path(__file__).parent / "mahiro_report"
        if res.exists():
            if self.resource_path.exists():
                shutil.rmtree(self.resource_path)
            shutil.move(res, self.resource_path)
            logger.info(f"移动 真寻日报 资源文件夹成功 {res} -> {self.resource_path}")

    async def remove(self):
        """移除资源"""
        if self.resource_path.exists():
            shutil.rmtree(self.resource_path)
            logger.info(f"删除 真寻日报 资源文件夹成功 {self.resource_path}")

class GroupManager:
    """群组管理器"""
    @staticmethod
    async def get_platform_groups(platform: str) -> List[str]:
        """获取指定平台的有效群组"""
        return await GroupConsole.filter(
            status=True,
            channel_id__isnull=True,
            platform=platform
        ).values_list("group_id", flat=True)

    @staticmethod
    async def is_group_enabled(bot: Bot, group_id: str) -> bool:
        """检查群组是否启用日报功能"""
        return not await CommonUtils.task_is_block(bot, "mahiro_report", group_id)

class BroadcastManager:
    """广播管理器"""
    def __init__(self, interval: int = 5):
        self.interval = interval
        self._semaphore = asyncio.Semaphore(5)

    async def send_to_group(self, bot: Bot, group_id: str, message) -> bool:
        """发送消息到单个群组"""
        try:
            if not await GroupManager.is_group_enabled(bot, group_id):
                logger.info(f"群 {group_id} 已禁用日报功能")
                return False
                
            await PlatformUtils.send_message(bot, None, group_id, message)
            return True
        except Exception as e:
            logger.error(f"向群 {group_id} 发送失败: {e}")
            return False

    async def broadcast(self, message) -> bool:
        """执行广播任务"""
        async with self._semaphore:
            bots = nonebot.get_bots()
            if not bots:
                logger.error("没有可用的Bot连接")
                return False

            success_count = 0
            fail_count = 0

            for bot in bots.values():
                platform = PlatformUtils.get_platform(bot)
                groups = await GroupManager.get_platform_groups(platform)
                
                if not groups:
                    logger.info(f"平台 {platform} 没有需要发送的群组")
                    continue

                for group_id in groups:
                    if await self.send_to_group(bot, group_id, message):
                        success_count += 1
                    else:
                        fail_count += 1
                    await asyncio.sleep(self.interval)

            logger.info(f"广播完成: 成功 {success_count}, 失败 {fail_count}")
            return success_count > 0

class DailyReportService:
    """日报服务"""
    def __init__(self):
        self.broadcast_manager = BroadcastManager()

    async def prepare_report(self) -> bool:
        """准备日报"""
        try:
            await Report.get_report_image()
            return True
        except Exception as e:
            logger.error(f"准备日报失败: {e}")
            return False

    async def broadcast_report(self) -> bool:
        """广播日报"""
        try:
            report_file = await Report.get_report_image()
            message = MessageUtils.build_message(report_file)
            return await self.broadcast_manager.broadcast(message)
        except Exception as e:
            logger.error(f"广播日报失败: {e}")
            return False

# 初始化服务
daily_report = DailyReportService()
report_command = ReportCommand()
resource_manager = ResourceManager()

# 注册定时任务
@scheduler.scheduled_job("cron", hour=9, minute=0)
async def broadcast_daily_report_task():
    """定时广播日报任务"""
    if await daily_report.broadcast_report():
        logger.info("日报广播成功")
    else:
        logger.error("日报广播失败")

@scheduler.scheduled_job("cron", hour=8, minute=30)
async def prepare_daily_report():
    """提前准备日报"""
    if await daily_report.prepare_report():
        logger.info("日报准备成功")
    else:
        logger.error("日报准备失败")
