from pathlib import Path
import shutil

from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_session import EventSession
from nonebot_plugin_apscheduler import scheduler

from zhenxun.configs.path_config import TEMPLATE_PATH
from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig, Task
from zhenxun.services.log import logger
from zhenxun.services.plugin_init import PluginInit
from zhenxun.utils.message import MessageUtils

from .utils import meal_reminder, MEAL_SCHEDULE, Meals, eating_manager


__plugin_meta__ = PluginMetadata(
    name="吃饭小助手",
    description="选择恐惧症？让Bot建议你今天吃什么！",
    usage="""
    指令：
        今天吃什么/中午吃啥/今晚吃啥/中午吃什么/晚上吃啥/晚上吃什么/夜宵吃啥
        菜单/群菜单/查看菜单
        [su] 添加/移除 菜名
        [su] 加菜 菜名
        [su] 基础菜单
        [su] 开启/关闭小助手
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2.6",
        superuser_help="""重置吃饭小助手""",
        commands=[
            Command(command="今天吃什么"),
            Command(command="菜单"),
            Command(command="添加"),
            Command(command="移除"),
            Command(command="加菜"),
            Command(command="基础菜单"),
            Command(command="开启小助手"),
            Command(command="关闭小助手"),
        ],
        tasks=[Task(module="what2eat", name="吃饭小助手")],
        configs=[
            RegisterConfig(
                module="what2eat",
                key="eating_limit",
                value=3,
                help="每日吃饭次数限制",
                default_value=3,
                type=int,
            ),
            RegisterConfig(
                module="what2eat",
                key="use_preset_menu",
                value=True,
                help="是否使用预设菜单",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                module="what2eat",
                key="use_preset_greating",
                value=True,
                help="是否使用预设问候语",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                module="what2eat",
                key="groups_id",
                value=[],
                help="需要发送提醒的群组ID列表",
                default_value=[],
                type=list,
            ),
        ],
    ).to_dict(),
)

RESOURCE_PATH = TEMPLATE_PATH / "what2eat" / "resource"

# 创建命令匹配器
what2eat_matcher = on_alconna(
    Alconna(
        "吃什么",
        "今天吃什么",
        "早餐吃什么",
        "早餐吃啥",
        "早上吃什么",
        "早上吃啥",
        "午餐吃什么",
        "午餐吃啥",
        "中午吃什么",
        "中午吃啥",
        "晚餐吃什么",
        "晚餐吃啥",
        "晚上吃什么",
        "晚上吃啥",
        "夜宵吃什么",
        "夜宵吃啥",
    ),
    priority=5,
    block=True,
)

menu_matcher = on_alconna(Alconna("群菜单", "查看菜单"), priority=5, block=True)

add_matcher = on_alconna(
    Alconna("添加", "移除"), priority=5, block=True, permission=SUPERUSER
)

add_base_matcher = on_alconna(
    Alconna("加菜"), priority=5, block=True, permission=SUPERUSER
)

base_menu_matcher = on_alconna(
    Alconna("基础菜单"), priority=5, block=True, permission=SUPERUSER
)

switch_matcher = on_alconna(
    Alconna("开启小助手", "关闭小助手"), priority=5, block=True, permission=SUPERUSER
)


@what2eat_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    """处理吃什么命令"""
    try:
        logger.info(f"吃什么命令: {arparma.header_result}")
        msg = eating_manager.get2eat(session)
        await MessageUtils.build_message(msg).send(reply_to=True)
        logger.info("查看今天吃什么", arparma.header_result, session=session)
    except Exception as e:
        logger.error(f"获取今天吃什么失败: {e}", arparma.header_result, session=session)


@menu_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    """处理菜单命令"""
    try:
        msg = eating_manager.get_menu(session)
        await MessageUtils.build_message(msg).send(reply_to=True)
        logger.info("查看菜单", arparma.header_result, session=session)
    except Exception as e:
        logger.error(f"获取菜单失败: {e}", arparma.header_result, session=session)


@add_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    """处理添加/移除命令"""
    try:
        action = "添加" if arparma.header_result == "添加" else "移除"
        args = arparma.args
        if not args:
            await MessageUtils.build_message(f"请输入要{action}的菜名").send()
            return
        msg = eating_manager.add_or_remove_dish(action, args[0])
        await MessageUtils.build_message(msg).send(reply_to=True)
        logger.info(f"{action}菜品", arparma.header_result, session=session)
    except Exception as e:
        logger.error(f"{action}菜品失败: {e}", arparma.header_result, session=session)


@add_base_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    """处理加菜命令"""
    try:
        args = arparma.args
        if not args:
            await MessageUtils.build_message("请输入要添加的菜名").send()
            return
        msg = eating_manager.add_to_base_menu(args[0])
        await MessageUtils.build_message(msg).send(reply_to=True)
        logger.info("添加基础菜品", arparma.header_result, session=session)
    except Exception as e:
        logger.error(f"添加基础菜品失败: {e}", arparma.header_result, session=session)


@base_menu_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    """处理基础菜单命令"""
    try:
        msg = eating_manager.get_base_menu()
        await MessageUtils.build_message(msg).send(reply_to=True)
        logger.info("查看基础菜单", arparma.header_result, session=session)
    except Exception as e:
        logger.error(f"获取基础菜单失败: {e}", arparma.header_result, session=session)


@switch_matcher.handle()
async def _(session: EventSession, arparma: Arparma):
    """处理开启/关闭小助手命令"""
    try:
        action = "开启" if arparma.header_result == "开启小助手" else "关闭"
        msg = meal_reminder.switch_reminder(action == "开启")
        await MessageUtils.build_message(msg).send(reply_to=True)
        logger.info(f"{action}小助手", arparma.header_result, session=session)
    except Exception as e:
        logger.error(f"{action}小助手失败: {e}", arparma.header_result, session=session)


class MyPluginInit(PluginInit):
    async def install(self):
        res = Path(__file__).parent / "what2eat"
        if res.exists():
            if RESOURCE_PATH.exists():
                shutil.rmtree(RESOURCE_PATH)
            shutil.move(res, RESOURCE_PATH)
            logger.info(f"移动 吃饭小助手 资源文件夹成功 {res} -> {RESOURCE_PATH}")

        # 注册定时任务
        try:
            for meal_type, cfg in MEAL_SCHEDULE.items():
                job_id = f"meal_reminder_{meal_type}"
                # 检查任务是否已存在
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
                scheduler.add_job(
                    meal_reminder.send_reminder,
                    "cron",
                    args=[meal_type],
                    hour=cfg["hour"],
                    minute=0,
                    id=job_id,
                )
            logger.info("成功注册吃饭提醒定时任务")
        except Exception as e:
            logger.error(f"注册吃饭提醒定时任务失败: {str(e)}")

    async def remove(self):
        if RESOURCE_PATH.exists():
            shutil.rmtree(RESOURCE_PATH)
            logger.info(f"删除 吃饭小助手 资源文件夹成功 {RESOURCE_PATH}")

        # 移除定时任务
        try:
            for meal_type in Meals:
                job_id = f"meal_reminder_{meal_type}"
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
            logger.info("成功移除吃饭提醒定时任务")
        except Exception as e:
            logger.error(f"移除吃饭提醒定时任务失败: {str(e)}")
