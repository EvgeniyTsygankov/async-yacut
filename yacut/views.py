import asyncio
import string
from secrets import choice

import requests
from flask import (
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for,
)

from . import app, db
from .constants import LENGTH_SHORT, MAX_TRIES
from .forms import FileForm, URLMapForm
from .models import URLMap
from .yandex_cloud import YandexDiskError, get_download_url, upload_many

ALPHABET = string.ascii_letters + string.digits


def _random_short(length: int) -> str:
    """Генерирует случайную строку заданной длины из символов алфавита."""
    return "".join(choice(ALPHABET) for _ in range(length))


def get_unique_short_id(length: int = LENGTH_SHORT) -> str:
    """Генерирует уникальный короткий идентификатор."""
    for _ in range(MAX_TRIES):
        code = _random_short(length)
        if not URLMap.query.filter_by(short=code).first():
            return code
    raise RuntimeError("Не удалось сгенерировать уникальный short_id")


@app.route("/", methods=["GET", "POST"])
def index_view():
    """
    Главная страница - создание коротких ссылок.

    Обрабатывает форму для создания коротких ссылок из длинных URL.
    """
    form = URLMapForm()
    short_link = None
    if form.validate_on_submit():
        original = form.original_link.data
        custom = form.custom_id.data or None
        short = custom if custom else get_unique_short_id()
        url_map = URLMap(original=original, short=short)
        db.session.add(url_map)
        db.session.commit()
        short_link = request.host_url + short
    return render_template(
        "converting_links.html",
        form=form,
        short_link=short_link,
        active_page="index",
    )


def _filename_from_disk_path(path: str) -> str:
    """
    Извлекает имя файла из пути на Яндекс.Диске.

    Убирает UUID префикс если он присутствует в формате 'uuid_filename'.
    """
    name = path.rsplit("/", 1)[-1]
    return name.split("_", 1)[1] if "_" in name else name


def _proxy_yadisk_download(href: str, original_path: str) -> Response:
    """Проксирует файл с Яндекс.Диска через сервер."""
    try:
        upstream = requests.get(href, stream=True, timeout=120)
    except requests.RequestException:
        abort(502)

    if upstream.status_code >= 400:
        abort(502)

    headers: dict[str, str] = {}
    for h in ("Content-Type", "Content-Length", "Content-Disposition"):
        v = upstream.headers.get(h)
        if v:
            headers[h] = v

    if "Content-Disposition" not in headers:
        headers["Content-Disposition"] = (
            f'attachment; filename="{_filename_from_disk_path(original_path)}"'
        )

    headers.setdefault("X-Accel-Buffering", "no")

    return Response(
        stream_with_context(upstream.iter_content(64 * 1024)),
        headers=headers,
        status=200,
    )


def _serve_yadisk_path(original_path: str, token: str) -> Response:
    """Обрабатывает скачивание файла с Яндекс.Диска."""
    try:
        href = asyncio.run(get_download_url(token, original_path))
    except Exception:
        abort(502)

    if current_app.config.get("DISK_DIRECT_REDIRECT"):
        return redirect(href, code=302)

    return _proxy_yadisk_download(href, original_path)


@app.route("/<string:short_id>", methods=["GET"])
@app.route("/<string:short_id>/", methods=["GET"])
def follow_short(short_id):
    """
    Обработчик перехода по короткой ссылке.

    Перенаправляет на оригинальный URL или скачивает файл с Яндекс.Диска.
    """
    if short_id.lower() == "files":
        return redirect(url_for("files_view"))

    url_map = URLMap.query.filter_by(short=short_id).first_or_404()
    original = url_map.original or ""

    if original.startswith(("http://", "https://")):
        return redirect(original, code=302)

    token = current_app.config.get("DISK_TOKEN") or ""
    if not token:
        abort(500)

    return _serve_yadisk_path(original, token)


def _render_files_page(form: FileForm, results=None):
    """Рендерит страницу загрузки файлов с переданными параметрами."""
    return render_template(
        "download_files.html",
        form=form,
        results=results,
        active_page="files",
    )


def _flash_and_render(form: FileForm, message: str, category: str):
    """Показывает flash-сообщение и рендерит страницу."""
    flash(message, category)
    return _render_files_page(form)


def _extract_files_from_form(form: FileForm):
    """
    Извлекает файлы из полей формы.

    Проверяет различные возможные имена полей с файлами.
    """
    files = []
    for field_name in ("files", "file"):
        if hasattr(form, field_name):
            data = getattr(form, field_name).data
            if isinstance(data, (list, tuple)):
                files = [f for f in data if getattr(f, "filename", "")]
            elif data and getattr(data, "filename", ""):
                files = [data]
            if files:
                break
    return files


def _extract_files_from_request():
    """
    Извлекает файлы непосредственно из request.files.

    Используется как fallback если файлы не найдены в форме.
    """
    return (
        request.files.getlist("files")
        or request.files.getlist("file")
        or list(request.files.values())
    )


def _warm_downloads_best_effort(token: str, items) -> None:
    """
    Предварительно получает ссылки для скачивания файлов.

    Выполняется в фоновом режиме, ошибки игнорируются.
    """
    async def _runner():
        await asyncio.gather(
            *(get_download_url(token, it.disk_path) for it in items),
            return_exceptions=True,
        )

    try:
        asyncio.run(_runner())
    except Exception:
        pass


def _create_short_links(items):
    """Создает короткие ссылки для загруженных файлов."""
    results = []
    for it in items:
        short = get_unique_short_id()
        db.session.add(URLMap(original=it.disk_path, short=short))
        results.append(
            {
                "filename": it.filename,
                "short_link": url_for(
                    "follow_short",
                    short_id=short,
                    _external=True
                ),
            }
        )
    db.session.commit()
    return results


@app.route("/files", methods=["GET", "POST"])
def files_view():
    """
    Страница загрузки файлов на Яндекс.Диск.

    Обрабатывает загрузку файлов и создание коротких ссылок для скачивания.
    """
    form = FileForm()

    if not form.validate_on_submit():
        return _render_files_page(form)

    token = current_app.config.get("DISK_TOKEN") or ""
    if not token:
        return _flash_and_render(
            form, "Токен Яндекс.Диска не настроен", "danger"
        )

    base_dir = current_app.config.get("DISK_BASE_DIR") or "app:"

    files = _extract_files_from_form(form) or _extract_files_from_request()
    if not files:
        return _flash_and_render(
            form,
            "Вы не выбрали файлы. Убедитесь, что форма отправляется как "
            "multipart/form-data.",
            "warning",
        )

    try:
        items = asyncio.run(upload_many(files, token, base_dir=base_dir))
    except YandexDiskError as e:
        return _flash_and_render(
            form, f"Не удалось загрузить файлы: {e}", "danger"
        )
    _warm_downloads_best_effort(token, items)
    results = _create_short_links(items)
    return _render_files_page(form, results)