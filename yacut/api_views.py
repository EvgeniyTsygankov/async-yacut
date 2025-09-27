import re

from flask import jsonify, request
from sqlalchemy.exc import IntegrityError

from . import app, db
from .constants import RESERVED_SHORTS
from .error_handlers import InvalidAPIUsageError
from .models import URLMap
from .views import get_unique_short_id


# Регулярное выражение для проверки формата короткой ссылки
# Допускаются буквы (A-Z, a-z) и цифры (0-9) длиной от 1 до 16 символов
SHORT_RE = re.compile(r'^[A-Za-z0-9]{1,16}$')


@app.route('/api/id/', methods=['POST'])
def add_short_id():
    """
    Создание новой короткой ссылки.

    Принимает JSON с обязательным полем 'url' и опциональным 'custom_id'.

    Возвращает созданную короткую ссылку и оригинальный URL.
    """
    if not request.is_json:
        raise InvalidAPIUsageError('Отсутствует тело запроса', 400)
    data = request.get_json(silent=True)
    if not data:
        raise InvalidAPIUsageError('Отсутствует тело запроса', 400)
    original = data.get('url')
    if not original:
        raise InvalidAPIUsageError('"url" является обязательным полем!', 400)
    custom = data.get('custom_id')
    if custom:
        if not SHORT_RE.fullmatch(custom):
            raise InvalidAPIUsageError(
                'Указано недопустимое имя для короткой ссылки', 400
            )
        if custom.lower() in RESERVED_SHORTS or URLMap.query.filter_by(
            short=custom
        ).first():
            raise InvalidAPIUsageError(
                'Предложенный вариант короткой ссылки уже существует.', 400
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
        url_map.short = get_unique_short_id()
        db.session.add(url_map)
        db.session.commit()

    return jsonify(
        {
            'short_link': request.host_url + url_map.short,
            'url': url_map.original}
    ), 201


@app.route('/api/id/<string:short_id>/', methods=['GET'])
def get_short_url(short_id):
    """
    Получение оригинального URL по короткому идентификатору.

    Возвращает оригинальный URL если короткая ссылка найдена.
    """
    url_map = URLMap.query.filter_by(short=short_id).first()
    if not url_map:
        raise InvalidAPIUsageError('Указанный id не найден', 404)
    return jsonify({'url': url_map.original}), 200