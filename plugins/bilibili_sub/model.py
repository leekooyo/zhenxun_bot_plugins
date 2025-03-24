from tortoise import fields

from zhenxun.services.db_context import Model
from zhenxun.services.log import logger


class BilibiliSub(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    sub_id = fields.CharField(255)
    """订阅id"""
    sub_type = fields.CharField(255)
    """订阅类型"""
    sub_users = fields.TextField()
    """订阅用户"""
    live_short_id = fields.IntField(null=True)
    """直播短id"""
    live_status = fields.IntField(null=True)
    """直播状态 0: 停播  1: 直播"""
    uid = fields.BigIntField(null=True)
    """主播/UP UID"""
    uname = fields.CharField(255, null=True)
    """主播/UP 名称"""
    latest_video_created = fields.BigIntField(null=True)
    """最后视频上传时间"""
    dynamic_upload_time = fields.BigIntField(null=True, default=0)
    """动态发布时间"""
    season_name = fields.CharField(255, null=True)
    """番剧名称"""
    season_id = fields.IntField(null=True)
    """番剧id"""
    season_current_episode = fields.CharField(255, null=True)
    """番剧最新集数"""
    season_update_time = fields.DateField(null=True)
    """番剧更新日期"""

    class Meta(Model.Meta):
        table = "bilibili_sub"
        table_description = "B站订阅数据表"
        unique_together = ("sub_id", "sub_type")

    @classmethod
    async def sub_handle(
        cls,
        sub_id: int,
        sub_type: str | None = None,
        sub_user: str = "",
        **kwargs,
    ) -> bool:
        """
        说明:
            添加订阅
        参数:
            :param sub_id: 订阅名称，房间号，番剧号等
            :param sub_type: 订阅类型
            :param sub_user: 订阅此条目的用户
            :param kwargs: 其他订阅相关参数
        """
        try:
            # 处理订阅用户格式
            formatted_sub_user = (
                f"{sub_user}," if sub_user and not sub_user.endswith(",") else sub_user
            )

            # 获取现有订阅
            existing_sub = await cls._get_existing_sub(sub_id, sub_type)

            # 准备更新数据
            update_data = cls._prepare_update_data(
                existing_sub=existing_sub,
                sub_type=sub_type,
                sub_user=formatted_sub_user,
                **kwargs,
            )

            # 创建或更新订阅
            if not existing_sub:
                await cls.create(
                    sub_id=sub_id, sub_type=sub_type, sub_users=formatted_sub_user
                )

            await cls.update_or_create(sub_id=sub_id, defaults=update_data)
            return True

        except Exception as e:
            logger.error(f"添加订阅失败: {type(e)}: {e}")
            return False

    @classmethod
    async def _get_existing_sub(
        cls, sub_id: int, sub_type: str | None
    ) -> "BilibiliSub | None":
        """获取现有订阅"""
        if sub_type:
            return await cls.get_or_none(sub_id=sub_id, sub_type=sub_type)
        return await cls.get_or_none(sub_id=sub_id)

    @classmethod
    def _prepare_update_data(
        cls,
        existing_sub: "BilibiliSub | None",
        sub_type: str | None,
        sub_user: str,
        **kwargs,
    ) -> dict:
        """准备更新数据"""
        if not existing_sub:
            return {"sub_type": sub_type, "sub_users": sub_user, **kwargs}

        return {
            "sub_type": sub_type or existing_sub.sub_type,
            "sub_users": existing_sub.sub_users + sub_user,
            "live_short_id": kwargs.get("live_short_id") or existing_sub.live_short_id,
            "live_status": kwargs.get("live_status")
            if kwargs.get("live_status") is not None
            else existing_sub.live_status,
            "dynamic_upload_time": kwargs.get("dynamic_upload_time")
            or existing_sub.dynamic_upload_time,
            "uid": kwargs.get("uid") or existing_sub.uid,
            "uname": kwargs.get("uname") or existing_sub.uname,
            "latest_video_created": kwargs.get("latest_video_created")
            or existing_sub.latest_video_created,
            "season_name": kwargs.get("season_name") or existing_sub.season_name,
            "season_id": kwargs.get("season_id") or existing_sub.season_id,
            "season_current_episode": kwargs.get("season_current_episode")
            or existing_sub.season_current_episode,
            "season_update_time": kwargs.get("season_update_time")
            or existing_sub.season_update_time,
        }

    @classmethod
    async def delete_bilibili_sub(
        cls, sub_id: int, sub_user: str, sub_type: str | None = None
    ) -> bool:
        """
        说明:
            删除指定用户的订阅
        参数:
            :param sub_id: 订阅名称
            :param sub_user: 要删除的用户 (格式: user_id:group_id 或 user_id)
            :param sub_type: 订阅类型
        """
        try:
            # 按 ID 和类型查找订阅
            if sub_type:
                sub = await cls.filter(sub_id=sub_id, sub_type=sub_type).first()
            else:
                sub = await cls.filter(sub_id=sub_id).first()

            if not sub:
                return False

            # 解析现有的订阅用户列表
            sub_users_list = sub.sub_users.split(",") if sub.sub_users else []
            # 获取当前群号
            current_group = sub_user.split(":")[-1] if ":" in sub_user else None
            # 过滤并保留订阅用户
            new_sub_users = [
                user for user in sub_users_list
                if user and (
                    (":" in user and user.split(":")[-1] != current_group) or
                    (":" not in user and user != sub_user)
                )
            ]

            if not new_sub_users:
                await sub.delete()
            else:
                # 按UID排序
                new_sub_users.sort(key=lambda x: int(x.split(":")[0] if ":" in x else x))
                # 更新订阅用户列表
                sub.sub_users = ",".join(new_sub_users) + ","
                await sub.save()
            return True
        except Exception as e:
            logger.error(f"bilibili_sub 删除订阅错误 {type(e)}: {e}")
        return False

    @classmethod
    async def get_all_sub_data(
        cls,
    ) -> tuple[list["BilibiliSub"], list["BilibiliSub"], list["BilibiliSub"]]:
        """
        说明:
            分类获取所有数据
        """
        live_data = []
        up_data = []
        season_data = []
        query = await cls.all()
        for x in query:
            if x.sub_type == "live":
                live_data.append(x)
            if x.sub_type == "up":
                up_data.append(x)
            if x.sub_type == "season":
                season_data.append(x)
        return live_data, up_data, season_data

    @classmethod
    async def _run_script(cls):
        return [
            "ALTER TABLE bilibili_sub "
            "ALTER COLUMN season_update_time TYPE timestamp with time zone "
            "USING season_update_time::timestamp with time zone;",
            "ALTER TABLE bilibili_sub ALTER COLUMN sub_id TYPE character varying(255);",
        ]
