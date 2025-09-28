from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, List
import uuid

import aiohttp
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


# Базовые константы для работы с API Яндекс.Диска
API_HOST = "https://cloud-api.yandex.net"
API_VERSION = "v1"
YANDEX_API = f"{API_HOST}/{API_VERSION}/disk"


@dataclass
class UploadItem:
    """Результат загрузки одного файла на Яндекс.Диск."""

    filename: str
    disk_path: str


class YandexDiskError(Exception):
    """Ошибка при работе с API Яндекс.Диска."""


def compose_path(base_dir: str, filename: str) -> str:
    """Создает безопасный путь для сохранения файла на Яндекс.Диске."""
    safe_name = secure_filename(filename) or "file"
    uid = uuid.uuid4().hex
    return f"{base_dir}/{uid}_{safe_name}"


async def _get_upload_href(
    session: aiohttp.ClientSession,
    token: str,
    path: str,
    overwrite: bool = True,
) -> str:
    """Получает URL для загрузки файла на Яндекс.Диск."""
    params = {"path": path, "overwrite": "true" if overwrite else "false"}
    headers = {"Authorization": f"OAuth {token}"}
    async with session.get(
        f"{YANDEX_API}/resources/upload", params=params, headers=headers
    ) as resp:
        if resp.status >= 400:
            try:
                detail = await resp.json()
            except Exception:
                detail = await resp.text()
            raise YandexDiskError(
                f"Failed to get upload href for {path}: {resp.status} {detail}"
            )
        data = await resp.json()
        href = data.get("href")
        if not href:
            raise YandexDiskError(f"Upload href missing for {path}")
        return href


async def _get_download_href(
    session: aiohttp.ClientSession,
    token: str,
    path: str,
) -> str:
    """Получает URL для скачивания файла с Яндекс.Диска."""
    headers = {"Authorization": f"OAuth {token}"}
    async with session.get(
        f"{YANDEX_API}/resources/download",
        params={"path": path},
        headers=headers
    ) as resp:
        if resp.status >= 400:
            try:
                detail = await resp.json()
            except Exception:
                detail = await resp.text()
            raise YandexDiskError(
                f"Failed to get download href for "
                f"{path}: {resp.status} {detail}"
            )
        data = await resp.json()
        href = data.get("href")
        if not href:
            raise YandexDiskError(f"Download href missing for {path}")
        return href


async def ensure_folder(
    session: aiohttp.ClientSession, token: str, folder: str
) -> None:
    """Создать папку, если её нет (201 — создано, 409 — уже существует)."""
    headers = {"Authorization": f"OAuth {token}"}
    async with session.put(
        f"{YANDEX_API}/resources", params={"path": folder}, headers=headers
    ) as resp:
        if resp.status in (201, 409):
            return
        if resp.status >= 400:
            try:
                detail = await resp.json()
            except Exception:
                detail = await resp.text()
            raise YandexDiskError(
                f"Failed to ensure folder {folder}: {resp.status} {detail}"
            )


async def upload_file(
    session: aiohttp.ClientSession,
    token: str,
    file: FileStorage,
    base_dir: str = "yacut",
) -> UploadItem:
    """Загрузить один файл и вернуть UploadItem с путём на диске."""
    path = compose_path(base_dir, file.filename)
    href = await _get_upload_href(session, token, path, overwrite=True)
    stream = getattr(file, "stream", None) or file
    try:
        stream.seek(0)
    except Exception:
        pass
    data = stream.read()
    headers = {
        "Content-Type": "application/octet-stream",
        "Authorization": f"OAuth {token}",
    }
    if isinstance(data, (bytes, bytearray)):
        headers["Content-Length"] = str(len(data))

    async with session.put(href, data=data, headers=headers) as put_resp:
        if put_resp.status not in (201, 202):
            try:
                detail = await put_resp.json()
            except Exception:
                detail = await put_resp.text()
            raise YandexDiskError(
                f"Failed to upload {file.filename}: {put_resp.status} {detail}"
            )
    return UploadItem(filename=file.filename, disk_path=path)


async def upload_many(
    files: Iterable[FileStorage], token: str, base_dir: str = "yacut"
) -> List[UploadItem]:
    """
    Параллельно загрузить несколько файлов. Возвращает список UploadItem.

    Если все загрузки упали — бросит YandexDiskError.
    """
    timeout = aiohttp.ClientTimeout(total=60 * 10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            upload_file(session, token, f, base_dir)
            for f in files
            if f and getattr(f, "filename", "")
        ]
        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: List[UploadItem] = []
        errors: List[str] = []
        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            elif isinstance(result, UploadItem):
                items.append(result)
        if errors and not items:
            raise YandexDiskError("; ".join(errors))
        return items


async def get_download_url(token: str, path_on_disk: str) -> str:
    """Получить одноразовый href для скачивания ранее загруженного файла."""
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        return await _get_download_href(session, token, path_on_disk)
