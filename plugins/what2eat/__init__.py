from nonebot import get_bot, on_command, on_regex, require
from nonebot.adapters.onebot.v11 import (
    Bot,
    GROUP,
    GROUP_ADMIN,
    GROUP_OWNER,
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
import asyncio
from typing import Set

from .utils import config, eating_manager, Meals

__zx_plugin_name__ = "吃饭小助手"
__plugin_usage__ = """
usage：
    选择恐惧症？让Bot建议你今天吃什么！吃什么：今天吃什么、中午吃啥、今晚吃啥、中午吃什么、晚上吃啥、晚上吃什么、夜宵吃啥……
    查看群菜单：菜单/群菜单/查看菜单；
    [su] 添加或移除：添加/移除 菜名；
    [su] 添加至基础菜单：加菜 菜名；
    [su] 查看基础菜单：基础菜单；
    [su] 开启/关闭按时吃饭小助手：开启/关闭小助手；
""".strip()
__plugin_des__ = "吃饭小助手"
__plugin_cmd__ = [
    "菜单/群菜单/查看菜单",
    "添加/移除",
    "加菜",
    "基础菜单",
    "开启/关闭小助手",
    "开启/关闭按时吃饭小助手",
]

greating_helper = require("nonebot_plugin_apscheduler").scheduler
eating_helper = require("nonebot_plugin_apscheduler").scheduler

__what2eat_version__ = "v0.2.6"
plugin_notes = f"""
今天吃什么？ {__what2eat_version__}
[xx吃xx]    问bot恰什么
[添加 xx]   添加菜品至群菜单
[移除 xx]   从菜单移除菜品
[加菜 xx]   添加菜品至基础菜单
[菜单]       查看群菜单
[基础菜单]查看基础菜单
[开启/关闭小助手]   开启/关闭按时吃饭小助手""".strip()

plugin_help = on_command("吃什么帮助", permission=GROUP, priority=5, block=True)
what2eat = on_regex(r"(\w*吃(?:什么|啥|点啥))", permission=GROUP, priority=5, block=True)

switch_greating = on_regex(
    r"(开启|关闭)小助手", 
    permission=SUPERUSER, 
    priority=5, 
    block=True
)
add_greating = on_command(
    "添加问候", 
    aliases={"添加问候语"}, 
    permission=SUPERUSER | GROUP_ADMIN | GROUP_OWNER, 
    priority=5, 
    block=True
)
remove_greating = on_command(
    "删除问候", 
    aliases={"删除问候语"}, 
    permission=SUPERUSER, 
    priority=5, 
    block=True
)

@plugin_help.handle()
async def handle_help(bot: Bot):
    await plugin_help.finish(plugin_notes)

@what2eat.handle()
async def handle_what2eat(bot: Bot, event: GroupMessageEvent):
    await what2eat.finish(message=MessageSegment.reply(event.message_id) + eating_manager.get2eat(event))

@switch_greating.handle()
async def handle_switch_greeting(bot: Bot, event: GroupMessageEvent):
    action = event.get_plaintext()[:2]
    if action == "开启":
        scheduler.resume()
        msg = "已开启按时吃饭小助手~"
    elif action == "关闭":
        scheduler.pause()
        msg = "已关闭按时吃饭小助手~"
    await switch_greating.finish(msg)

@add_greating.handle()
async def handle_add_greeting(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    args = args.extract_plain_text().strip().split()
    if not args or len(args) != 2:
        await add_greating.finish("请输入正确的参数格式：类别 问候语")
        return
    await add_greating.finish(eating_manager.add_greating(args))

@remove_greating.handle()
async def handle_remove_greeting(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    args = args.extract_plain_text().strip().split()
    if not args or len(args) > 1:
        await remove_greating.finish("请输入删除问候语的类别~")
        return
    await remove_greating.finish(eating_manager.remove_greating(args[0]))

# 定时任务配置
MEAL_SCHEDULE = {
    Meals.BREAKFAST: {"hour": 7, "name": "早餐"},
    Meals.LUNCH: {"hour": 12, "name": "午餐"},
    Meals.SNACK: {"hour": 15, "name": "下午茶"},
    Meals.DINNER: {"hour": 18, "name": "晚餐"},
    Meals.MIDNIGHT: {"hour": 21, "name": "夜宵"}
}

scheduler = require("nonebot_plugin_apscheduler").scheduler
semaphore, running_tasks = asyncio.Semaphore(3), set()
task_locks = {meal: asyncio.Lock() for meal in Meals}

async def send_meal_reminder(meal_type: Meals) -> None:
    """发送定时提醒消息
    Args:
        meal_type (Meals): 餐次类型
    """
    if meal_type in running_tasks: return
    
    async with semaphore, task_locks[meal_type]:
        try:
            running_tasks.add(meal_type)
            msg = eating_manager.get2greating(meal_type)
            if msg and config.groups_id:
                bot = get_bot()
                meal_name = MEAL_SCHEDULE[meal_type]['name']
                for gid in config.groups_id:
                    try:
                        await bot.send_group_msg(group_id=int(gid), message=msg)
                    except Exception as e:
                        logger.error(f"发送{meal_name}提醒到群{gid}失败: {e}")
                logger.info(f"已群发{meal_name}提醒")
        except Exception as e:
            logger.error(f"{MEAL_SCHEDULE[meal_type]['name']}提醒任务执行失败: {e}")
        finally:
            running_tasks.remove(meal_type)

# 注册定时任务
for meal_type, cfg in MEAL_SCHEDULE.items():
    @scheduler.scheduled_job("cron", hour=cfg["hour"], minute=0, id=f"meal_reminder_{meal_type}")
    async def handle_meal_reminder(): await send_meal_reminder(meal_type)

@scheduler.scheduled_job("cron", hour="6,11,17,22", minute=0)
async def handle_reset_eating_count() -> None:
    """重置每日吃什么次数"""
    try:
        eating_manager.reset_eating()
        logger.info("今天吃什么次数已刷新")
    except Exception as e:
        logger.error(f"重置吃什么次数失败: {e}")