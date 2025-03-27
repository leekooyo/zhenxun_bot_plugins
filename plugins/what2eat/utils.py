"""
Author: xx
Date: 2025-03-22 16:02:14
LastEditors: Do not edit
LastEditTime: 2025-03-27 18:10:49
Description: 吃饭小助手工具类
"""

from nonebot_plugin_session import EventSession
from nonebot import logger
import random
from pathlib import Path
from typing import Optional, List, Set
from enum import Enum
import asyncio
from pydantic import BaseModel, Field
from zhenxun.configs.config import Config
from zhenxun.utils.platform import broadcast_group

try:
    import ujson as json
except ModuleNotFoundError:
    import json


class What2EatConfig(BaseModel):
    """吃饭小助手配置"""

    eating_limit: int = 3
    """每日吃饭次数限制"""
    use_preset_menu: bool = True
    """是否使用预设菜单"""
    use_preset_greating: bool = True
    """是否使用预设问候语"""
    groups_id: List[int] = Field(default_factory=list)
    """需要发送提醒的群组ID列表"""


# 获取配置
what2eat_config = Config.get("what2eat")


def get_groups_id() -> List[int]:
    """
    获取需要发送提醒的群组ID列表
    """
    return what2eat_config.get("groups_id", [])


class Meals(Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    SNACK = "snack"
    DINNER = "dinner"
    MIDNIGHT = "midnight"


MEAL_SCHEDULE = {
    Meals.BREAKFAST: {"hour": 7, "name": "早餐"},
    Meals.LUNCH: {"hour": 12, "name": "午餐"},
    Meals.SNACK: {"hour": 15, "name": "下午茶"},
    Meals.DINNER: {"hour": 18, "name": "晚餐"},
    Meals.MIDNIGHT: {"hour": 21, "name": "夜宵"},
}


class EatingManager:
    def __init__(self, path: Optional[Path]):
        self.greating_enbale = True
        self._data = {}
        self._greating = {}
        if not path:
            logger.info(Path(__file__).parent)
            data_file = Path(__file__).parent / "resource" / "data.json"
            greating_file = Path(__file__).parent / "resource" / "greating.json"
        else:
            data_file = path / "data.json"
            greating_file = path / "greating.json"

        self.data_file = data_file
        self.greating_file = greating_file

        if data_file.exists():
            with open(data_file, encoding="utf-8") as f:
                self._data = json.load(f)

        if greating_file.exists():
            with open(greating_file, encoding="utf-8") as f:
                self._greating = json.load(f)

        self._init_json()

    def _init_json(self) -> None:
        if "basic_food" not in self._data.keys():
            self._data["basic_food"] = []
        if "group_food" not in self._data.keys():
            self._data["group_food"] = {}
        if "eating" not in self._data.keys():
            self._data["eating"] = {}

        for meal in Meals:
            if meal.value not in self._greating.keys():
                self._greating[meal.value] = []

    def _init_data(self, group_id: str, user_id: str) -> None:
        """
        初始化用户信息
        """
        if group_id not in self._data["group_food"].keys():
            self._data["group_food"][group_id] = []
        if group_id not in self._data["eating"].keys():
            self._data["eating"][group_id] = {}
        if user_id not in self._data["eating"][group_id].keys():
            self._data["eating"][group_id][user_id] = 0

    def get2eat(self, session: EventSession) -> str:
        """
        今天吃什么
        """
        user_id = str(session.id1)
        group_id = str(session.id2)

        self._init_data(group_id, user_id)
        if (
            len(self._data["basic_food"]) == 0
            and len(self._data["group_food"][group_id]) == 0
        ):
            return "还没有菜单呢，就先饿着肚子吧，请[添加 菜名]🤤"

        food_list = self._data["basic_food"].copy()
        if len(self._data["group_food"][group_id]) > 0:
            food_list.extend(self._data["group_food"][group_id])

        msg = "建议" + random.choice(food_list)
        self._data["eating"][group_id][user_id] += 1
        self.save()

        return msg

    def food_exists(self, _food_: str) -> int:
        """
        检查菜品是否存在
        1:  存在于基础菜单
        2:  存在于群菜单
        0:  不存在
        """
        for food in self._data["basic_food"]:
            if food == _food_:
                return 1

        for group_id in self._data["group_food"]:
            for food in self._data["group_food"][group_id]:
                if food == _food_:
                    return 2

        return 0

    def eating_check(self, session: EventSession) -> bool:
        """
        检查是否吃饱
        """
        user_id = str(session.id1)
        group_id = str(session.id2)
        eating_limit = what2eat_config.get("eating_limit", 3)
        return (
            False if self._data["eating"][group_id][user_id] >= eating_limit else True
        )

    def add_or_remove_dish(self, action: str, dish: str) -> str:
        """
        添加或移除菜品
        """
        if action == "添加":
            return self.add_basic_food(dish)
        else:
            return self.remove_food(dish)

    def add_to_base_menu(self, dish: str) -> str:
        """
        添加至基础菜单
        """
        return self.add_basic_food(dish)

    def add_basic_food(self, new_food: str) -> str:
        """
        添加至基础菜单 SUPERUSER 权限
        """
        status = self.food_exists(new_food)
        if status == 1:
            return f"{new_food} 已在基础菜单中~"
        elif status == 2:
            return f"{new_food} 已在群特色菜单中~"

        self._data["basic_food"].append(new_food)
        self.save()
        return f"{new_food} 已加入基础菜单~"

    def remove_food(self, food_to_remove: str) -> str:
        """
        从基础菜单移除 SUPERUSER 权限
        """
        status = self.food_exists(food_to_remove)
        if not status:
            return f"{food_to_remove} 不在菜单中哦~"

        # 在基础菜单
        if status == 1:
            self._data["basic_food"].remove(food_to_remove)
            self.save()
            return f"{food_to_remove} 已从基础菜单中删除~"
        # 在群菜单
        else:
            for group_id in self._data["group_food"]:
                if food_to_remove in self._data["group_food"][group_id]:
                    self._data["group_food"][group_id].remove(food_to_remove)
                    self.save()
                    return f"{food_to_remove} 已从群菜单中删除~"

    def reset_eating(self) -> None:
        """
        重置用户食用次数
        """
        for group_id in self._data["eating"]:
            for user_id in self._data["eating"][group_id]:
                self._data["eating"][group_id][user_id] = 0
        self.save()

    def save(self) -> None:
        """
        保存数据
        """
        with open(self.data_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(self._data, ensure_ascii=False, indent=4))
            f.close()
        with open(self.greating_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(self._greating, ensure_ascii=False, indent=4))
            f.close()

    def get_menu(self, session: EventSession) -> str:
        """
        获取群菜单
        """
        group_id = str(session.id2)
        user_id = str(session.id1)

        if group_id not in self._data["group_food"]:
            self._init_data(group_id, user_id)

        if not self._data["group_food"][group_id]:
            return "群菜单为空，请使用[加菜 菜名]添加菜品~"

        msg = "群特色菜单：\n"
        for food in self._data["group_food"][group_id]:
            msg += f"- {food}\n"
        return msg

    def get_base_menu(self) -> str:
        """
        获取基础菜单
        """
        if not self._data["basic_food"]:
            return "基础菜单为空，请使用[加菜 菜名]添加菜品~"

        msg = "基础菜单：\n"
        for food in self._data["basic_food"]:
            msg += f"- {food}\n"
        return msg

    def get2greating(self, meal: Meals) -> Optional[str]:
        """
        获取问候语
        """
        if not self._greating[meal.value]:
            return None
        return random.choice(self._greating[meal.value])

    def add_greating(self, args: List) -> str:
        """
        添加问候语
        """
        if len(args) != 2:
            return "请输入正确的参数格式：类别 问候语"

        meal_type = args[0]
        greating = args[1]

        if meal_type not in [meal.value for meal in Meals]:
            return f"不支持的类别：{meal_type}"

        self._greating[meal_type].append(greating)
        self.save()
        return f"已添加{meal_type}的问候语：{greating}"

    def remove_greating(self, arg: str) -> str:
        """
        删除问候语
        """
        if arg not in [meal.value for meal in Meals]:
            return f"不支持的类别：{arg}"

        if not self._greating[arg]:
            return f"{arg}没有问候语~"

        self._greating[arg] = []
        self.save()
        return f"已删除{arg}的所有问候语~"


class MealReminderManager:
    """用于管理定时提醒任务的类"""

    def __init__(self):
        self.semaphore = asyncio.Semaphore(3)
        self.running_tasks: Set[Meals] = set()
        self.task_locks = {meal: asyncio.Lock() for meal in Meals}
        self.is_enabled = True

    async def send_reminder(self, meal_type: Meals) -> None:
        """发送定时提醒消息"""
        if not self.is_enabled or meal_type in self.running_tasks:
            return

        async with self.semaphore, self.task_locks[meal_type]:
            try:
                self.running_tasks.add(meal_type)
                msg = eating_manager.get2greating(meal_type)
                groups_id = get_groups_id()
                if not msg or not groups_id:
                    return

                meal_name = MEAL_SCHEDULE[meal_type]["name"]
                failed_groups = []

                for gid in groups_id:
                    try:
                        await broadcast_group(msg, group_id=int(gid))
                    except Exception as e:
                        failed_groups.append(gid)
                        logger.error(f"发送{meal_name}提醒到群{gid}失败: {str(e)}")

                if failed_groups:
                    logger.warning(
                        f"{meal_name}提醒发送失败的群: {', '.join(map(str, failed_groups))}"
                    )
                else:
                    logger.info(f"已成功群发{meal_name}提醒")

            except Exception as e:
                logger.error(
                    f"{MEAL_SCHEDULE[meal_type]['name']}提醒任务执行失败: {str(e)}"
                )
            finally:
                self.running_tasks.discard(meal_type)

    def switch_reminder(self, enable: bool) -> str:
        """开启或关闭定时提醒"""
        self.is_enabled = enable
        status = "开启" if enable else "关闭"
        return f"已{status}按时吃饭小助手~"


# 创建全局实例
eating_manager = EatingManager(None)
meal_reminder = MealReminderManager()
