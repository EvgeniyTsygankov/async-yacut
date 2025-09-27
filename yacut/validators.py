from pathlib import Path

from wtforms.validators import ValidationError

from .constants import ALLOWED_EXTS


def validate_files(self, field):
    """
    Кастомный валидатор для проверки загружаемых файлов.

    Проверяет расширения файлов на соответствие разрешенным.
    """
    files = field.data or []
    if not files:
        raise ValidationError('Выберите хотя бы один файл')
    bad = []
    for f in files:
        ext = (Path(f.filename).suffix or '').lstrip('.').lower()
        if ext not in ALLOWED_EXTS:
            bad.append(f'.{ext}' if ext else f.filename)
    if bad:
        raise ValidationError('Недопустимые типы файлов: ' + ', '.join(bad))