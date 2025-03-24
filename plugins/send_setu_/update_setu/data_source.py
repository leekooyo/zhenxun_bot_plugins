from datetime import datetime
import os
import shutil
from pathlib import Path

import aiofiles
from asyncpg.exceptions import UniqueViolationError
import nonebot
from nonebot.drivers import Driver
from PIL import UnidentifiedImageError
import ujson as json

from zhenxun.configs.path_config import IMAGE_PATH, TEMP_PATH, TEXT_PATH
from zhenxun.services.log import logger
from zhenxun.utils._build_image import BuildImage
from zhenxun.utils.http_utils import AsyncHttpx
from zhenxun.utils.utils import change_pixiv_image_links

from .._model import Setu

driver: Driver = nonebot.get_driver()

_path = IMAGE_PATH


# 替换旧色图数据，修复local_id一直是50的问题
@driver.on_startup
async def update_old_setu_data():
    path = TEXT_PATH
    setu_data_file = path / "setu_data.json"
    r18_data_file = path / "r18_setu_data.json"
    if setu_data_file.exists() or r18_data_file.exists():
        index = 0
        r18_index = 0
        count = 0
        fail_count = 0
        for file in [setu_data_file, r18_data_file]:
            if file.exists():
                data = json.load(open(file, encoding="utf8"))
                for x in data:
                    if file == setu_data_file:
                        idx = index
                        if "R-18" in data[x]["tags"]:
                            data[x]["tags"].remove("R-18")
                    else:
                        idx = r18_index
                    img_url = (
                        data[x]["img_url"].replace("i.pixiv.cat", "i.pximg.net")
                        if "i.pixiv.cat" in data[x]["img_url"]
                        else data[x]["img_url"]
                    )
                    # idx = r18_index if 'R-18' in data[x]["tags"] else index
                    try:
                        if not await Setu.exists(pid=data[x]["pid"], url=img_url):
                            await Setu.create(
                                local_id=idx,
                                title=data[x]["title"],
                                author=data[x]["author"],
                                pid=data[x]["pid"],
                                img_hash=data[x]["img_hash"],
                                img_url=img_url,
                                is_r18="R-18" in data[x]["tags"],
                                tags=",".join(data[x]["tags"]),
                            )
                        count += 1
                        if "R-18" in data[x]["tags"]:
                            r18_index += 1
                        else:
                            index += 1
                        logger.info(
                            f'添加旧色图数据成功 PID：{data[x]["pid"]} index：{idx}....'
                        )
                    except UniqueViolationError:
                        fail_count += 1
                        logger.info(
                            "添加旧色图数据失败，"
                            f'色图重复 PID：{data[x]["pid"]} index：{idx}...'
                        )
                file.unlink()
        setu_url_path = path / "setu_url.json"
        setu_r18_url_path = path / "setu_r18_url.json"
        if setu_url_path.exists():
            setu_url_path.unlink()
        if setu_r18_url_path.exists():
            setu_r18_url_path.unlink()
        logger.info(
            f"更新旧色图数据完成，成功更新数据：{count} 条，累计失败：{fail_count} 条"
        )


# 删除色图rar文件夹
shutil.rmtree(IMAGE_PATH / "setu_rar", ignore_errors=True)
shutil.rmtree(IMAGE_PATH / "r18_rar", ignore_errors=True)
shutil.rmtree(IMAGE_PATH / "rar", ignore_errors=True)

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.6;"
    " rv:2.0.1) Gecko/20100101 Firefox/4.0.1",
    "Referer": "https://www.pixiv.net",
}


async def update_setu_img(flag: bool = False) -> str | None:
    """更新色图

    参数:
        flag: 是否手动更新.

    返回:
        str | None: 更新信息
    """
    image_list = await Setu.all().order_by("local_id")
    image_list.reverse()
    _success = 0
    error_info = []
    error_type = []
    count = 0
    for image in image_list:
        count += 1
        path = _path / "_r18" if image.is_r18 else _path / "_setu"
        local_image = path / f"{image.local_id}.jpg"
        path.mkdir(exist_ok=True, parents=True)
        TEMP_PATH.mkdir(exist_ok=True, parents=True)
        
        async def process_image(image, path: Path, local_image: Path) -> bool:
            """处理单个图片，返回是否成功"""
            if local_image.exists() and image.img_hash:
                logger.info(f"更新色图 {image.local_id}.jpg 已存在")
                return False
            
            temp_file = TEMP_PATH / f"{image.local_id}.jpg"
            if temp_file.exists():
                temp_file.unlink()
            
            url_ = change_pixiv_image_links(image.img_url)
            try:
                if not await AsyncHttpx.download_file(url_, temp_file):
                    return False
                
                # 处理图片大小
                img = BuildImage.open(temp_file)
                if os.path.getsize(temp_file) > 1024 * 1024 * 1.5:
                    await img.resize(0.9)
                
                # 统一使用 save_image 处理所有图片保存
                if not await save_image(img, local_image):
                    return False
                
                image.img_hash = ""
                await image.save(update_fields=["img_hash"])
                return True
            
            except UnidentifiedImageError:
                if local_image.exists():
                    async with aiofiles.open(local_image) as f:
                        if "404 Not Found" in await f.read():
                            local_image.unlink()
                            max_num = await Setu.delete_image(image.pid, image.img_url)
                            if (path / f"{max_num}.jpg").exists():
                                os.rename(path / f"{max_num}.jpg", local_image)
                                logger.warning(f"更新色图 PID：{image.pid} 404，已删除并替换")
                return False
            
            except OSError as e:
                if "cannot write mode RGBA as JPEG" in str(e):
                    logger.warning(f"检测到RGBA格式图片 {image.local_id}.jpg，尝试转换...")
                    try:
                        img = BuildImage.open(temp_file)
                        if await save_image(img, local_image):
                            return True
                    except Exception as convert_error:
                        logger.error(f"转换RGBA图片失败: {convert_error}")
                else:
                    logger.error(f"更新色图 {image.local_id}.jpg 错误 OSError: {e}")
                    if type(e) not in error_type:
                        error_type.append(type(e))
                        error_info.append(f"更新色图 {image.local_id}.jpg 错误 OSError: {e}")
                return False
            
            except Exception as e:
                logger.error(f"更新色图 {image.local_id}.jpg 错误 {type(e)}: {e}")
                if type(e) not in error_type:
                    error_type.append(type(e))
                    error_info.append(f"更新色图 {image.local_id}.jpg 错误 {type(e)}: {e}")
                return False

        if await process_image(image, path, local_image):
            _success += 1

    if _success or error_info or flag:
        text = (
            f'{str(datetime.now()).split(".")[0]} 更新 色图 完成，本地存在 {count} 张，'
        )
        return f"{text}实际更新 {_success} 张，以下为更新时未知错误：\n" + "\n".join(
            error_info
        )

    return None

async def save_image(img: BuildImage, save_path: Path) -> bool:
    """保存图片，处理RGBA格式"""
    try:
        if img.markImg.mode == 'RGBA':
            # 创建白色背景
            background = BuildImage(
                width=img.width,
                height=img.height,
                color='white',
                mode='RGB'
            )
            # BuildImage.paste() 会自动处理 RGBA 的 alpha 通道
            # 不需要显式传递 mask 参数
            await background.paste(img, (0, 0))
            await background.save(save_path)
        else:
            await img.save(save_path)
        return True
    except Exception as e:
        logger.error(f"保存图片失败 {save_path.name}: {type(e)}: {e}")
        return False
