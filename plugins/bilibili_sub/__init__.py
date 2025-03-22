import asyncio
import time
import traceback
from datetime import datetime
from io import BytesIO

import nonebot
from arclet.alconna.typing import CommandMeta
from bilireq.login import Login
from nonebot.adapters.onebot.v11 import Bot
from nonebot.drivers import Driver
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import ArgStr
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_session import EventSession

from zhenxun.configs.config import Config
from zhenxun.configs.utils import PluginExtraData, RegisterConfig
from zhenxun.models.group_console import GroupConsole
from zhenxun.services.log import logger  # noqa: F811
from zhenxun.utils.image_utils import text2image
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .auth import AuthManager
from .data_source import (
    BilibiliSub,
    SubManager,
    add_live_sub,
    add_season_sub,
    add_up_sub,
    get_media_id,
    get_sub_status,
)
from .utils import calc_time_total

base_config = Config.get("bilibili_sub")

__plugin_meta__ = PluginMetadata(
    name="B站订阅",
    description="非常便利的B站订阅通知",
    usage="""
        usage：
            B站直播，番剧，UP动态开播等提醒
            主播订阅相当于 直播间订阅 + UP订阅
            指令：
                添加订阅 ['主播'/'UP'/'番剧'] [id/链接/番名]
                删除订阅 ['主播'/'UP'/'id'] [id]
                查看订阅
            示例：
                添加订阅主播 2345344 <-(直播房间id)
                添加订阅UP 2355543 <-(个人主页id)
                添加订阅番剧 史莱姆 <-(支持模糊搜索)
                添加订阅番剧 125344 <-(番剧id)
                删除订阅id 2324344 <-(任意id，通过查看订阅获取)
        """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.4",
        superuser_help="""
    登录b站获取cookie防止风控：
            bil_check/检测b站
            bil_login/登录b站
            bil_logout/退出b站 uid
            示例:
                登录b站 
                检测b站
                bil_logout 12345<-(退出登录的b站uid，通过检测b站获取)
        """,
        configs=[
            RegisterConfig(
                module="bilibili_sub",
                key="LIVE_MSG_AT_ALL",
                value=False,
                help="直播提醒是否AT全体（仅在真寻是管理员时生效）",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="UP_MSG_AT_ALL",
                value=False,
                help="UP动态投稿提醒是否AT全体（仅在真寻是管理员时生效）",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="CHECK_TIME",
                value=60,
                help="b站检测时间间隔(秒)",
                default_value=60,
                type=int,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="ENABLE_SLEEP_MODE",
                value=True,
                help="是否开启固定时间段内休眠",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="SLEEP_START_TIME",
                value="01:00",
                help="开启休眠时间",
                default_value="01:00",
                type=str,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="SLEEP_END_TIME",
                value="07:30",
                help="关闭休眠时间",
                default_value="07:30",
                type=str,
            ),
            RegisterConfig(
                module="bilibili_sub",
                key="ENABLE_AD_FILTER",
                value=True,
                help="是否开启广告过滤",
                default_value=True,
                type=bool,
            ),
        ],
        admin_level=base_config.get("GROUP_BILIBILI_SUB_LEVEL"),
    ).to_dict(),
)

Config.add_plugin_config(
    "bilibili_sub",
    "GROUP_BILIBILI_SUB_LEVEL",
    0,
    help="群内bilibili订阅需要管理的权限",
    default_value=0,
    type=int,
)

add_sub = on_alconna(
    Alconna(
        "添加订阅",
        Args["sub_type", str]["sub_msg", str],
        meta=CommandMeta(compact=True),
    ),
    aliases={"d", "添加订阅"},
    priority=0,
    block=True,
)
del_sub = on_alconna(
    Alconna(
        "删除订阅",
        Args["sub_type", str]["sub_msg", str],
        meta=CommandMeta(compact=True),
    ),
    aliases={"td", "取消订阅"},
    priority=0,
    block=True,
)
show_sub_info = on_alconna("查看订阅", priority=5, block=True)

blive_check = on_alconna(
    Alconna("bil_check"),
    aliases={"检测b站", "检测b站登录", "b站登录检测"},
    permission=SUPERUSER,
    priority=0,
    block=True,
)
blive_login = on_alconna(
    Alconna("bil_login"),
    aliases={"登录b站", "b站登录"},
    permission=SUPERUSER,
    priority=0,
    block=True,
)
blive_logout = on_alconna(
    Alconna("bil_logout", Args["uid", int]),
    aliases={"退出b站", "退出b站登录", "b站登录退出"},
    permission=SUPERUSER,
    priority=0,
    block=True,
)

driver: Driver = nonebot.get_driver()

sub_manager: SubManager | None = None


@driver.on_startup
async def _():
    global sub_manager
    sub_manager = SubManager()
    await sub_manager.reload_sub_data()  # 确保数据被加载


@add_sub.handle()
@del_sub.handle()
async def _(session: EventSession, state: T_State, sub_type: str, sub_msg: str):
    gid = session.id3 or session.id2
    if gid:
        sub_user = f"{session.id1}:{gid}"
    else:
        sub_user = f"{session.id1}"
    state["sub_type"] = sub_type
    state["sub_user"] = sub_user
    if "http" in sub_msg:
        sub_msg = sub_msg.split("?")[0]
        sub_msg = sub_msg[:-1] if sub_msg[-1] == "/" else sub_msg
        sub_msg = sub_msg.split("/")[-1]
    id_ = sub_msg[2:] if sub_msg.startswith("md") else sub_msg
    if not id_.isdigit():
        if sub_type in ["season", "动漫", "番剧"]:
            rst = "*以为您找到以下番剧，请输入Id选择：*\n"
            state["season_data"] = await get_media_id(id_)
            if len(state["season_data"]) == 0:
                await MessageUtils.build_message(f"未找到番剧：{sub_msg}").finish()
            for i, x in enumerate(state["season_data"]):
                rst += f"{i + 1}.{state['season_data'][x]['title']}\n----------\n"
            await MessageUtils.build_message("\n".join(rst.split("\n")[:-1])).send()
        else:
            await MessageUtils.build_message("Id 必须为全数字！").finish()
    else:
        state["id"] = int(id_)


@add_sub.got("sub_type")
@add_sub.got("sub_user")
@add_sub.got("id")
async def _(
    session: EventSession,
    state: T_State,
    id_: str = ArgStr("id"),
    sub_type: str = ArgStr("sub_type"),
    sub_user: str = ArgStr("sub_user"),
):
    if sub_type in ["season", "动漫", "番剧"] and state.get("season_data"):
        season_data = state["season_data"]
        if not id_.isdigit() or int(id_) < 1 or int(id_) > len(season_data):
            await add_sub.reject_arg("id", "Id必须为数字且在范围内！请重新输入...")
        sub_id = int(season_data[int(id_) - 1]["media_id"])
    else:
        sub_id = int(id_)

    if sub_type in ["主播", "直播"]:
        await MessageUtils.build_message(await add_live_sub(sub_id, sub_user)).send()
    elif sub_type.lower() in ["up", "用户"]:
        await MessageUtils.build_message(await add_up_sub(sub_id, sub_user)).send()
    elif sub_type in ["season", "动漫", "番剧"]:
        await MessageUtils.build_message(await add_season_sub(sub_id, sub_user)).send()
    else:
        await MessageUtils.build_message(
            "参数错误，第一参数必须为：主播/up/番剧！"
        ).finish()
    gid = session.id3 or session.id2
    logger.info(
        f"(USER {session.id1}, GROUP "
        f"{gid if gid else 'private'})"
        f" 添加订阅：{sub_type} -> {sub_user} -> {sub_id}"
    )


@del_sub.got("sub_type")
@del_sub.got("sub_user")
@del_sub.got("id")
async def _(
    session: EventSession,
    id_: str = ArgStr("id"),
    sub_type: str = ArgStr("sub_type"),
    sub_user: str = ArgStr("sub_user"),
):
    if sub_type in ["主播", "直播"]:
        result = await BilibiliSub.delete_bilibili_sub(int(id_), sub_user, "live")
    elif sub_type.lower() in ["up", "用户"]:
        result = await BilibiliSub.delete_bilibili_sub(int(id_), sub_user, "up")
    else:
        result = await BilibiliSub.delete_bilibili_sub(int(id_), sub_user)
    if result:
        await MessageUtils.build_message(f"删除订阅id：{id_} 成功...").send()
        gid = session.id3 or session.id2
        logger.info(
            f"(USER {session.id1}, GROUP {gid if gid else 'private'}) 删除订阅 {id_}"
        )
    else:
        await MessageUtils.build_message(f"删除订阅id：{id_} 失败...").send()


async def format_subscription_info(sub_data: BilibiliSub) -> tuple[str, str, str]:
    """
    格式化单个订阅信息

    Args:
        sub_data: 订阅数据对象

    Returns:
        tuple[str, str, str]: 直播、UP主、番剧的格式化信息
    """
    live_info = up_info = season_info = ""

    if sub_data.sub_type == "live":
        live_info = f"\t直播间id：{sub_data.sub_id}\n\t名称：{sub_data.uname}\n"
    elif sub_data.sub_type == "up":
        up_info = f"\tUP：{sub_data.uname}\n\tuid：{sub_data.uid}\n"
    elif sub_data.sub_type == "season":
        season_info = (
            f"\t番剧id：{sub_data.sub_id}\n"
            f"\t番名：{sub_data.season_name}\n"
            f"\t当前集数：{sub_data.season_current_episode}\n"
        )

    return live_info, up_info, season_info


async def format_subscription_list(
    subscriptions: list[BilibiliSub], gid: str | None
) -> str:
    """
    格式化订阅列表信息

    Args:
        subscriptions: 订阅数据列表
        gid: 群组ID，如果是私聊则为None

    Returns:
        str: 格式化后的订阅信息
    """
    if not subscriptions:
        return "该群目前没有任何订阅..." if gid else "您目前没有任何订阅..."

    # 分类存储不同类型的订阅信息
    subscription_info = {"live": [], "up": [], "season": []}

    # 处理每个订阅
    for sub in subscriptions:
        live_info, up_info, season_info = await format_subscription_info(sub)
        if live_info:
            subscription_info["live"].append(live_info)
        if up_info:
            subscription_info["up"].append(up_info)
        if season_info:
            subscription_info["season"].append(season_info)

    # 组装最终结果
    divider = "------------------\n"
    sections = []

    if subscription_info["live"]:
        sections.append(f"当前订阅的直播：\n{divider.join(subscription_info['live'])}")
    if subscription_info["up"]:
        sections.append(f"当前订阅的UP：\n{divider.join(subscription_info['up'])}")
    if subscription_info["season"]:
        sections.append(
            f"当前订阅的番剧：\n{divider.join(subscription_info['season'])}"
        )

    return "\n\n".join(sections)


@show_sub_info.handle()
async def _(session: EventSession):
    """显示用户或群组的订阅信息"""
    # 获取用户/群组ID
    gid = session.id3 or session.id2
    id_ = gid if gid else session.id1

    # 获取并格式化订阅数据
    subscriptions = await BilibiliSub.filter(sub_users__contains=id_).all()
    content = await format_subscription_list(subscriptions, gid)

    # 生成并发送图片
    img = await text2image(content, padding=10, color="#f9f6f2")
    await MessageUtils.build_message(img).finish()


@blive_check.handle()
async def _():
    if not AuthManager.grpc_auths:
        await MessageUtils.build_message("没有缓存的登录信息").finish()
    msgs = []
    for auth in AuthManager.grpc_auths:
        token_time = calc_time_total(auth.tokens_expired - int(time.time()))
        cookie_time = calc_time_total(auth.cookies_expired - int(time.time()))
        msg = (
            f"账号uid: {auth.uid}\n"
            f"token有效期: {token_time}\n"
            f"cookie有效期: {cookie_time}"
        )
        msgs.append(msg)
    await MessageUtils.build_message("\n----------\n".join(msgs)).finish()


@blive_login.handle()
async def _(matcher: Matcher):
    login = Login()
    qr_url = await login.get_qrcode_url()
    logger.debug(f"qrcode login url: {qr_url}")
    img = await login.get_qrcode(qr_url)
    if not img:
        await MessageUtils.build_message("获取二维码失败").finish()
    buffered = BytesIO()
    img.save(buffered, format="PNG")  # type:ignore
    img_data = buffered.getvalue()
    await MessageUtils.build_message(img_data).send()
    try:
        auth = await login.qrcode_login(interval=5)
        assert auth, "登录失败，返回数据为空"
        logger.debug(f"登录返回数据: {auth.data}")
        AuthManager.add_auth(auth)
    except Exception as e:
        await MessageUtils.build_message(f"登录失败: {e}").finish()
    await MessageUtils.build_message("登录成功，已将验证信息缓存至文件").finish()


@blive_logout.handle()
async def _(uid: int):
    if msg := AuthManager.remove_auth(uid):
        await MessageUtils.build_message(msg).finish()
    await MessageUtils.build_message(f"账号 {uid} 已退出登录").finish()


def should_run():
    """判断当前时间是否在运行时间段内（7点30到次日1点）"""
    now = datetime.now().time()
    # 如果当前时间在 7:30 到 23:59:59 之间，或者 0:00 到 1:00 之间，则运行
    return (
        now >= datetime.strptime(base_config.get("SLEEP_END_TIME"), "%H:%M").time()
    ) or (now < datetime.strptime(base_config.get("SLEEP_START_TIME"), "%H:%M").time())


semaphore = asyncio.Semaphore(150)


async def process_single_subscription(bot, sub) -> None:
    """
    处理单个订阅的逻辑
    """
    try:
        logger.info(f"Bilibili订阅开始检测：{sub.sub_id}，类型：{sub.sub_type}")

        async def check_status():
            if msg_list := await get_sub_status(sub.sub_id, sub.sub_type):
                await send_sub_msg(msg_list, sub, bot)

            # 如果是直播订阅，额外检查UP主动态
            if sub.sub_type == "live":
                if up_msg_list := await get_sub_status(sub.sub_id, "up"):
                    await send_sub_msg(up_msg_list, sub, bot)

        await asyncio.wait_for(check_status(), timeout=30)

    except asyncio.TimeoutError:
        logger.error(f"任务超时：检测订阅 {sub.sub_id} 时超时")
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(
            f"处理订阅时出错：{sub.sub_id}, 错误：{e}\n详细信息：\n{error_details}"
        )


@scheduler.scheduled_job(
    "interval",
    seconds=4,
    misfire_grace_time=30,
    max_instances=30,
    coalesce=True,
)
async def check_subscriptions():
    """
    定时任务：检查订阅并发送消息
    """
    try:
        async with semaphore:
            # 检查是否在休眠时间
            if base_config.get("ENABLE_SLEEP_MODE") and not should_run():
                return

            # 获取可用的机器人
            bots = nonebot.get_bots()
            if not bots:
                logger.warning("No available bots found.")
                return

            # 确保sub_manager已初始化
            if sub_manager is None:
                logger.error("SubManager not initialized")
                return

            # 获取订阅数据
            sub = await sub_manager.random_sub_data()
            if not sub:
                logger.info("No subscription data available.")
                return

            # 对每个可用的机器人处理订阅
            for bot in bots.values():
                if bot:
                    await process_single_subscription(bot, sub)

    except Exception as e:
        logger.error(f"检查订阅任务整体异常：{e}")


async def send_sub_msg(msg_list: list, sub: BilibiliSub, bot: Bot):
    """
    推送订阅消息到群组或私聊

    Args:
        msg_list (list): 待发送的消息列表
        sub (BilibiliSub): 订阅信息对象
        bot (Bot): 机器人实例
    """
    if not msg_list:
        return

    processed_groups = set()

    for user in sub.sub_users.split(",")[:-1]:
        try:
            # 处理群消息
            if ":" in user:
                _, group_id = user.split(":")

                if group_id in processed_groups:
                    continue
                processed_groups.add(group_id)

                # 检查插件是否被禁用
                if await GroupConsole.is_block_plugin(group_id, "bilibili_sub"):
                    continue

                messages = msg_list.copy()

                # 检查是否需要 at 全体
                try:
                    bot_role = (
                        await bot.get_group_member_info(
                            group_id=int(group_id),
                            user_id=int(bot.self_id),
                            no_cache=True,
                        )
                    )["role"]

                    if bot_role in ["owner", "admin"]:
                        should_at_all = (
                            sub.sub_type == "live"
                            and Config.get_config("bilibili_sub", "LIVE_MSG_AT_ALL")
                        ) or (
                            sub.sub_type == "up"
                            and Config.get_config("bilibili_sub", "UP_MSG_AT_ALL")
                        )
                        if should_at_all:
                            messages.insert(0, UniMessage.at_all() + "\n")
                except Exception as e:
                    logger.warning(f"获取机器人权限失败: {e}")

                # 发送群消息
                await PlatformUtils.send_message(
                    bot,
                    user_id=None,
                    group_id=group_id,
                    message=MessageUtils.build_message(messages),
                )

            # 处理私聊消息
            else:
                await PlatformUtils.send_message(
                    bot,
                    user_id=user,
                    group_id=None,
                    message=MessageUtils.build_message(msg_list),
                )

        except Exception as e:
            logger.error(
                f"B站订阅推送失败 - sub_id: {sub.sub_id}, 错误类型: {type(e)}, 错误信息: {e}"
            )
