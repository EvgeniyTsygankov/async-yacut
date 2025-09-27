import re

from flask import jsonify, request
from sqlalchemy.exc import IntegrityError

from . import app, db
from .constants import RESERVED_SHORTS
from .models import URLMap
from .views import get_unique_short_id


# Регулярное выражение для проверки формата короткой ссылки
# Допускаются буквы (A-Z, a-z) и цифры (0-9) длиной от 1 до 16 символов
SHORT_RE = re.compile(r'^[A-Za-z0-9]{1,16}$')


def _bad_request(message: str, code: int = 400):
    return jsonify(message=message), code


@app.route('/api/id/', methods=['POST'])
def add_short_id():
    """
    Создание короткой ссылки.

    Ожидает JSON {"url": "...", "custom_id": "..."?}
    Успех: 201, {"short_link": "...", "url": "..."}
    Ошибка: 400, {"message": "..."}
    """
    data = request.get_json(silent=True)
    if not data:
        return _bad_request('Отсутствует тело запроса')

    original = data.get('url')
    if not original:
        return _bad_request('"url" является обязательным полем!')

    custom = data.get('custom_id')
    if custom:
        if not SHORT_RE.fullmatch(custom):
            return _bad_request('Указано недопустимое имя для короткой ссылки')
        if custom.lower() in RESERVED_SHORTS or URLMap.query.filter_by(
            short=custom
        ).first():
            return _bad_request(
                'Предложенный вариант короткой ссылки уже существует.'
            )
        short = custom
    else:
        short = get_unique_short_id()

    url_map = URLMap(original=original, short=short)
    db.session.add(url_map)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not custom:
            url_map.short = get_unique_short_id()
            db.session.add(url_map)
            db.session.commit()
        else:
            return _bad_request(
                'Предложенный вариант короткой ссылки уже существует.'
            )

    return jsonify(
        short_link=request.host_url.rstrip('/') + '/' + url_map.short,
        url=url_map.original
    ), 201


@app.route('/api/id/<string:short_id>/', methods=['GET'])
def get_short_url(short_id):
    """
    Получение оригинального URL по короткому идентификатору.

    Возвращает оригинальный URL если короткая ссылка найдена.
    """
    obj = URLMap.query.filter_by(short=short_id).first()
    if not obj:
        return jsonify(message='Указанный id не найден'), 404
    return jsonify(url=obj.original), 200