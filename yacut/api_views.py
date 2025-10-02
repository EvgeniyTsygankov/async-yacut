from flask import jsonify, request

from . import app
from .constants import RESERVED_SHORTS
from .error_handlers import ModelValidationError
from .models import URLMap


def _bad_request(message: str, code: int = 400):
    return jsonify(message=message), code


@app.route('/api/id/', methods=['POST'])
def add_short_id():
    """
    Создание короткой ссылки.

    Ожидает JSON {"url": "...", "custom_id": "..."?}
    Успех: 201 -> {"short_link": "...", "url": "..."}
    Ошибка: 400 -> {"message": "..."}
    """
    data = request.get_json(silent=True)
    if not data:
        return _bad_request('Отсутствует тело запроса')

    original = data.get('url')
    if not original:
        return _bad_request('"url" является обязательным полем!')
    custom = (data.get('custom_id') or '').strip()
    try:
        url_map = (
            URLMap()
            .from_dict({'original': original, 'short': custom})
            .save(
                generate_short=URLMap.generate_unique_short,
                reserved_shorts=RESERVED_SHORTS,
            )
        )
    except ModelValidationError as e:
        return _bad_request(e.message, getattr(e, 'status_code', 400))
    return jsonify(
        short_link=request.host_url.rstrip('/') + '/' + url_map.short,
        url=url_map.original,
    ), 201


@app.route('/api/id/<string:short_id>/', methods=['GET'])
def get_short_url(short_id):
    """
    Получение оригинального URL по короткому идентификатору.

    Возвращает оригинальный URL если короткая ссылка найдена.
    """
    obj = URLMap.get(short_id)
    if obj is None:
        return jsonify(message='Указанный id не найден'), 404
    return jsonify(url=obj.original), 200