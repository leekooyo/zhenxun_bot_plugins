import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, TypedDict, Optional
from contextlib import contextmanager

import jmcomic
import pyminizip
from jmcomic import JmAlbumDetail
from nonebot.adapters.onebot.v11 import Bot
from pikepdf import Encryption, Pdf

from zhenxun.configs.path_config import DATA_PATH, TEMP_PATH
from zhenxun.services.log import logger
from zhenxun.utils.platform import PlatformUtils
from zhenxun.utils.utils import ResourceDirManager


IMAGE_OUTPUT_PATH = TEMP_PATH / "jmcomic"
IMAGE_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

PDF_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_pdf"
ZIP_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_zip"
PDF_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
ZIP_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

OPTION_FILE = Path(__file__).parent / "option.yml"


ResourceDirManager.add_temp_dir(PDF_OUTPUT_PATH)


option = jmcomic.create_option_by_file(str(OPTION_FILE.absolute()))


@dataclass
class DetailInfo:
    bot: Bot
    user_id: str
    group_id: Optional[str]
    album_id: str
    
    def get_file_name(self) -> str:
        return f"{self.album_id}.zip"
    
    def get_paths(self) -> tuple[Path, Path, Path]:
        pdf_path = PDF_OUTPUT_PATH / f"{self.album_id}.pdf"
        zip_path = ZIP_OUTPUT_PATH / f"{self.album_id}.zip"
        encrypted_pdf_path = PDF_OUTPUT_PATH / f"encrypted_{self.album_id}.pdf"
        return pdf_path, zip_path, encrypted_pdf_path

class DownloadTask(TypedDict):
    pending_users: list[DetailInfo]
    retry_count: int
    

class CreateZip:
    def __init__(self, data: DetailInfo):
        self.data = data
        self.password = data.album_id
        self.pdf_path, self.zip_path, self.encrypted_pdf_path = data.get_paths()

    @contextmanager
    def _pdf_context(self):
        try:
            with Pdf.open(self.pdf_path) as pdf:
                yield pdf
        finally:
            if self.pdf_path.exists():
                self.pdf_path.unlink()

    def encrypt_pdf(self) -> None:
        with self._pdf_context() as pdf:
            pdf.save(
                self.encrypted_pdf_path,
                encryption=Encryption(user=self.password, owner=self.password, R=6),
            )
        logger.info(f"PDF 已加密并保存到: {self.encrypted_pdf_path}", "jmcomic")

    def create_password_protected_zip(self):
        """创建带密码的 ZIP 文件"""
        pyminizip.compress(
            str(self.encrypted_pdf_path.absolute()),
            None,
            str(self.zip_path.absolute()),
            self.password,
            5,
        )
        logger.info(f"ZIP 文件已创建并加密: {self.zip_path}", "jmcomic")

    def create(self) -> Path:
        self.encrypt_pdf()
        self.create_password_protected_zip()
        return self.zip_path


class JmDownload:
    _data: ClassVar[dict[str, DownloadTask]] = {}
    MAX_RETRIES = 3

    @classmethod
    async def upload_file(cls, data: DetailInfo, zip_path: Optional[Path] = None) -> bool:
        try:
            if zip_path is None:
                zip_path = CreateZip(data).create()
            
            if not zip_path.exists():
                raise FileNotFoundError("ZIP文件不存在")

            api_name = "upload_group_file" if data.group_id else "upload_private_file"
            target_id = data.group_id if data.group_id else data.user_id
            
            await data.bot.call_api(
                api_name,
                group_id=target_id if data.group_id else None,
                user_id=target_id if not data.group_id else None,
                file=f"file:///{zip_path.absolute()}",
                name=data.get_file_name(),
            )
            return True
            
        except Exception as e:
            logger.error(
                "上传文件失败",
                "jmcomic",
                session=data.user_id,
                group_id=data.group_id,
                e=e,
            )
            await PlatformUtils.send_message(
                bot=data.bot,
                user_id=data.user_id,
                group_id=data.group_id,
                message=f"上传文件失败: {str(e)}",
            )
            return False

    @classmethod
    def call_send(cls, album: JmAlbumDetail, dler):
        data_list = cls._data.get(album.id)
        if not data_list:
            return
        try:
            loop = asyncio.get_running_loop()
        except Exception:
            loop = None
        for data in data_list:
            if loop:
                loop.create_task(cls.upload_file(data))
            else:
                asyncio.run(cls.upload_file(data))
        del cls._data[album.id]

    @classmethod
    async def download_album(cls, bot: Bot, user_id: str, group_id: Optional[str], album_id: str):
        zip_path = ZIP_OUTPUT_PATH / f"{album_id}.zip"

        if zip_path.exists():
            await cls.upload_file(
                DetailInfo(bot=bot, user_id=user_id, group_id=group_id, album_id=album_id),
                zip_path=zip_path
            )
            return

        if album_id not in cls._data:
            cls._data[album_id] = DownloadTask(pending_users=[], retry_count=0)
            
        cls._data[album_id]["pending_users"].append(
            DetailInfo(bot=bot, user_id=user_id, group_id=group_id, album_id=album_id)
        )
        
        try:
            await asyncio.to_thread(
                jmcomic.download_album, album_id, option, callback=cls.call_send
            )
        except Exception as e:
            if cls._data[album_id]["retry_count"] < cls.MAX_RETRIES:
                cls._data[album_id]["retry_count"] += 1
                await cls.download_album(bot, user_id, group_id, album_id)
            else:
                del cls._data[album_id]
                logger.error(f"下载失败，已达到最大重试次数: {e}", "jmcomic")