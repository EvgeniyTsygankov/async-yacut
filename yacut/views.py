import asyncio

from flask import (
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for
)
import requests

from . import app, db
from . import yandex_cloud as yc
from .constants import RESERVED_SHORTS
from .error_handlers import ModelValidationError
from .forms import FileForm, URLMapForm
from .models import URLMap


@app.route("/", methods=["GET", "POST"])
def index_view():
    """Главная страница: создание коротких ссылок для URL."""
    form = URLMapForm()
    short_link = None

    if form.validate_on_submit():
        original = form.original_link.data
        custom = (form.custom_id.data or "").strip()
        try:
            url_map = (
                URLMap()
                .from_dict({"original": original, "short": custom})
                .save(
                    generate_short=URLMap.generate_unique_short,
                    reserved_shorts=RESERVED_SHORTS,
                )
            )
        except ModelValidationError as e:
            flash(e.message, "danger")
            return render_template(
                "converting_links.html",
                form=form,
                short_link=None,
                active_page="index",
            )
        short_link = request.host_url + url_map.short
    return render_template(
        "converting_links.html",
        form=form,
        short_link=short_link,
        active_page="index",
    )


def _filename_from_disk_path(path: str) -> str:
    """Извлекает оригинальное имя файла из пути Яндекс.Диска."""
    name = path.rsplit("/", 1)[-1]
    return name.split("_", 1)[1] if "_" in name else name


def _proxy_yadisk_download(href: str, original_path: str) -> Response:
    """Проксирует скачивание файла с Яндекс.Диска через сервер."""
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
    """Обрабатывает скачивание файла с Яндекс Диска."""
    try:
        href = asyncio.run(yc.get_download_url(token, original_path))
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

    Для обычных URL - редирект на оригинальный адрес.
    Для путей Яндекс.Диска - скачивание файла.
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
    """Утилита для рендеринга страницы загрузки файлов."""
    return render_template(
        "download_files.html",
        form=form,
        results=results,
        active_page="files",
    )


def _flash_and_render(form: FileForm, message: str, category: str):
    """Утилита для показа flash-сообщения и рендеринга страницы."""
    flash(message, category)
    return _render_files_page(form)


def _extract_files_from_form(form: FileForm):
    """Извлекает файлы из формы, поддерживая разные имена полей."""
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
    """Извлекает файлы напрямую из request.files (fallback)."""
    return (
        request.files.getlist("files")
        or request.files.getlist("file")
        or list(request.files.values())
    )


def _create_short_links(items, token: str):
    """Создаёт короткие ссылки для переданных элементов и сохраняет их в БД."""
    results = []
    for it in items:
        short = URLMap.generate_unique_short()
        db.session.add(URLMap(original=it.disk_path, short=short))
        try:
            asyncio.run(yc.get_download_url(token, it.disk_path))
        except Exception:
            pass

        results.append({
            'filename': it.filename,
            'short': short,
        })
    db.session.commit()
    return results


@app.route("/files", methods=["GET", "POST"])
def files_view():
    """Страница загрузки файлов на Яндекс.Диск и генерации коротких ссылок."""
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
        items = asyncio.run(yc.upload_many(files, token, base_dir=base_dir))
    except yc.YandexDiskError as error:
        return _flash_and_render(
            form, f"Не удалось загрузить файлы: {error}", "danger"
        )
    results = _create_short_links(items, token)
    return _render_files_page(form, results)