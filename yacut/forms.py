from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, MultipleFileField
from wtforms import StringField, SubmitField, URLField
from wtforms.validators import (
    URL,
    DataRequired,
    Length,
    Optional,
    Regexp,
    ValidationError
)

from .constants import (
    ALLOWED_EXTS,
    RESERVED_SHORTS,
    SHORT_AUTO_GENERATE_LENGTH
)


class URLMapForm(FlaskForm):
    """Форма для создания коротких ссылок."""

    original_link = URLField(
        'Длинная ссылка',
        validators=[
            DataRequired(message='Обязательное поле'),
            URL(message='Некорректная ссылка, укажите http(s)://')
        ]
    )
    custom_id = StringField(
        'Ваш вариант короткой ссылки',
        validators=[
            Optional(),
            Length(
                max=SHORT_AUTO_GENERATE_LENGTH,
                message='Не более 6 символов'
            ),
            Regexp(r'^[A-Za-z0-9]+$', message='Только латинские буквы и цифры')
        ]
    )
    submit = SubmitField('Создать')

    def validate_custom_id(self, field):
        """Кастомный валидатор для проверки короткого идентификатора.

        Проверяет, что custom_id не зарезервирован и не существует в базе.
        """
        data = field.data
        if not data:
            return
        if data.lower() in RESERVED_SHORTS:
            raise ValidationError(
                'Предложенный вариант короткой ссылки уже существует.'
            )
        from yacut.models import URLMap
        if URLMap.query.filter_by(short=data).first():
            raise ValidationError(
                'Предложенный вариант короткой ссылки уже существует.'
            )


class FileForm(FlaskForm):
    """Форма для загрузки одного или нескольких файлов."""

    files = MultipleFileField(
        'Файлы',
        validators=[
            DataRequired(message='Выберите хотя бы один файл'),
            FileAllowed(
                ALLOWED_EXTS,
                message=(
                    'Выберите файлы с расширением: ' + ', '.join(
                        '.' + e for e in ALLOWED_EXTS
                    )
                )
            ),
        ]
    )
    submit = SubmitField('Загрузить')