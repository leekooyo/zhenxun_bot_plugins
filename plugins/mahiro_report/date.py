from datetime import date, timedelta
from typing import List, Tuple, Dict

import chinese_calendar as calendar
import lunardate

class FestivalManager:
    """节日管理器"""
    # 农历节日配置
    LUNAR_FESTIVALS: Dict[str, Tuple[int, int]] = {
        "春节": (1, 1),
        "端午节": (5, 5),
        "中秋节": (8, 15),
    }

    # 固定日期节日配置
    FIXED_FESTIVALS: Dict[str, Tuple[int, int]] = {
        "劳动节": (5, 1),
        "国庆节": (10, 1),
        "元旦": (1, 1),
    }

    @staticmethod
    def get_lunar_date(year: int, month: int, day: int) -> date:
        """获取农历日期对应的公历日期"""
        return lunardate.LunarDate(year, month, day).toSolarDate()

    @staticmethod
    def get_spring_equinox(year: int) -> date:
        """获取春分日期"""
        start_date = date(year, 3, 20)
        return next(
            (start_date + timedelta(days=i) for i in range(3)
             if calendar.get_holiday_detail(start_date + timedelta(days=i))[1] == "春分"),
            start_date
        )

    @staticmethod
    def get_tomb_sweeping_day(year: int) -> date:
        """获取清明节日期"""
        return FestivalManager.get_spring_equinox(year) + timedelta(days=15)

    @classmethod
    def get_next_festival_date(cls, festival_name: str, current_date: date) -> date:
        """获取下一个节日日期"""
        if festival_name in cls.LUNAR_FESTIVALS:
            month, day = cls.LUNAR_FESTIVALS[festival_name]
            next_year = current_date.year + 1
            return cls.get_lunar_date(next_year, month, day)
        
        if festival_name in cls.FIXED_FESTIVALS:
            month, day = cls.FIXED_FESTIVALS[festival_name]
            return current_date.replace(year=current_date.year + 1, month=month, day=day)
        
        if festival_name == "清明节":
            return cls.get_tomb_sweeping_day(current_date.year + 1)
        
        raise ValueError(f"未知的节日: {festival_name}")

    @classmethod
    def get_days_until_festival(cls, festival_name: str, today: date, festival_date: date) -> int:
        """计算距离节日的天数"""
        if festival_date < today:
            next_date = cls.get_next_festival_date(festival_name, festival_date)
            return (next_date - today).days
        return (festival_date - today).days

    @classmethod
    def get_all_festival_dates(cls, today: date) -> List[Tuple[int, str]]:
        """获取所有节日日期"""
        # 获取农历节日日期
        lunar_dates = {
            name: cls.get_lunar_date(today.year, month, day)
            for name, (month, day) in cls.LUNAR_FESTIVALS.items()
        }
        
        # 获取固定日期节日
        fixed_dates = {
            name: date(today.year, month, day)
            for name, (month, day) in cls.FIXED_FESTIVALS.items()
        }
        
        # 添加清明节
        lunar_dates["清明节"] = cls.get_tomb_sweeping_day(today.year)
        
        # 合并所有节日日期
        all_dates = {**lunar_dates, **fixed_dates}
        
        # 按优先级排序的节日名称
        priority_order = ["春节", "端午节", "中秋节", "清明节", "劳动节", "国庆节", "元旦"]
        
        # 计算并排序节日
        festival_days = [
            (cls.get_days_until_festival(name, today, date), name)
            for name in priority_order
            if name in all_dates
        ]
        
        return sorted(festival_days, key=lambda x: x[0])

def get_festivals_dates() -> List[Tuple[int, str]]:
    """获取节日日期列表"""
    return FestivalManager.get_all_festival_dates(date.today())
