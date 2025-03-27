from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional, List, Tuple

from nonebot_plugin_htmlrender import template_to_pic
from zhdate import ZhDate

from zhenxun.configs.config import Config
from zhenxun.configs.path_config import TEMPLATE_PATH
from zhenxun.utils._build_image import BuildImage
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.services.log import logger

from .config import REPORT_PATH, Anime, Hitokoto, SixData
from .date import get_festivals_dates

class BaseDataSource:
    """数据源基类"""
    def __init__(self):
        self.timeout = 10

class HitokotoSource(BaseDataSource):
    """一言数据源"""
    url = "https://v1.hitokoto.cn/?c=a"

    async def get_data(self) -> str:
        try:
            res = await AsyncHttpx.get(self.url, timeout=self.timeout)
            data = Hitokoto(**res.json())
            return data.hitokoto
        except Exception as e:
            logger.error(f"获取一言失败: {e}")
            return "今天也要元气满满哦！"

class BiliSource(BaseDataSource):
    """哔哩哔哩热搜数据源"""
    url = "https://s.search.bilibili.com/main/hotword"

    async def get_data(self) -> List[str]:
        try:
            res = await AsyncHttpx.get(self.url, timeout=self.timeout)
            data = res.json()
            return [item["keyword"] for item in data["list"]]
        except Exception as e:
            logger.error(f"获取哔哩哔哩热搜失败: {e}")
            return []

class AlapiSource(BaseDataSource):
    """Alapi数据源"""
    url = "https://v3.alapi.cn/api/zaobao"

    async def get_data(self) -> List[str]:
        try:
            token = Config.get_config("alapi", "ALAPI_TOKEN")
            if not token:
                return []
            payload = {"token": token, "format": "json"}
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            res = await AsyncHttpx.post(self.url, data=payload, headers=headers, timeout=self.timeout)
            if res.status_code != 200:
                return []
            data = res.json()
            news_items = data.get("data", {}).get("news", [])
            return news_items[:11]
        except Exception as e:
            logger.error(f"获取Alapi数据失败: {e}")
            return []

class SixSource(BaseDataSource):
    """60s数据源"""
    url = "https://60s.viki.moe/?v2=1"

    async def get_data(self) -> List[str]:
        try:
            if Config.get_config("alapi", "ALAPI_TOKEN"):
                alapi = AlapiSource()
                return await alapi.get_data()
            res = await AsyncHttpx.get(self.url, timeout=self.timeout)
            data = SixData(**res.json())
            return data.data.news[:11]
        except Exception as e:
            logger.error(f"获取60s数据失败: {e}")
            return []

class ITSource(BaseDataSource):
    """IT资讯数据源"""
    url = "https://www.ithome.com/rss/"

    async def get_data(self) -> List[str]:
        try:
            res = await AsyncHttpx.get(self.url, timeout=self.timeout)
            root = ET.fromstring(res.text)
            titles = []
            for item in root.findall("./channel/item"):
                title_element = item.find("title")
                if title_element is not None:
                    titles.append(title_element.text)
            return titles[:11]
        except Exception as e:
            logger.error(f"获取IT资讯失败: {e}")
            return []

class AnimeSource(BaseDataSource):
    """动漫数据源"""
    url = "https://api.bgm.tv/calendar"

    async def get_data(self) -> List[Tuple[str, str]]:
        try:
            res = await AsyncHttpx.get(self.url, timeout=self.timeout)
            data_list = []
            week = datetime.now().weekday()
            try:
                anime = Anime(**res.json()[week])
            except IndexError:
                anime = Anime(**res.json()[-1])
            data_list.extend(
                (data.name_cn or data.name, data.image) for data in anime.items
            )
            return data_list[:8]
        except Exception as e:
            logger.error(f"获取动漫数据失败: {e}")
            return []

class Report:
    """报告生成器"""
    def __init__(self):
        self.hitokoto = HitokotoSource()
        self.bili = BiliSource()
        self.six = SixSource()
        self.it = ITSource()
        self.anime = AnimeSource()
        self.week = {
            0: "一", 1: "二", 2: "三", 3: "四",
            4: "五", 5: "六", 6: "日"
        }

    async def get_report_image(self) -> Path:
        """获取报告图片"""
        now = datetime.now()
        file = REPORT_PATH / f"{now.date()}.png"
        if file.exists():
            return file

        # 清理旧文件
        for f in REPORT_PATH.iterdir():
            f.unlink()

        # 获取数据
        zhdata = ZhDate.from_datetime(now)
        data = {
            "data_festival": get_festivals_dates(),
            "data_hitokoto": await self.hitokoto.get_data(),
            "data_bili": await self.bili.get_data(),
            "data_six": await self.six.get_data(),
            "data_anime": await self.anime.get_data(),
            "data_it": await self.it.get_data(),
            "week": self.week[now.weekday()],
            "date": now.date(),
            "zh_date": zhdata.chinese().split()[0][5:],
            "full_show": Config.get_config("mahiro_report", "full_show"),
        }

        # 生成图片
        try:
            image_bytes = await template_to_pic(
                template_path=str((TEMPLATE_PATH / "mahiro_report").absolute()),
                template_name="main.html",
                templates={"data": data},
                pages={
                    "viewport": {"width": 578, "height": 1885},
                    "base_url": f"file://{TEMPLATE_PATH}",
                },
                wait=2,
            )
            await BuildImage.open(image_bytes).save(file)
            return file
        except Exception as e:
            logger.error(f"生成报告图片失败: {e}")
            raise

    @classmethod
    async def get_report_image(cls) -> Path:
        """类方法获取报告图片"""
        return await cls().get_report_image()
