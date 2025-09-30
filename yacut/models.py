from datetime import datetime, timezone
from secrets import choice
import string
from typing import Callable, Iterable, Optional

from sqlalchemy.exc import IntegrityError
from yacut import db

from .constants import (
    MAX_LENGHT_SHORT_LINK,
    MAX_TRIES,
    SHORT_AUTO_GENERATE_LENGTH,
    SHORT_RE
)
from .error_handlers import ModelValidationError


# Алфавит для генерации коротких ссылок (латинские буквы + цифры)
ALPHABET = string.ascii_letters + string.digits





class URLMap(db.Model):
    """
    Модель для представления коротких ссылок в базе данных.

    Содержит оригинальные ссылки и их короткие идентификаторы.
    """

    SHORT_EXISTS_MSG = "Предложенный вариант короткой ссылки уже существует."
    INVALID_SHORT_MSG = "Указано недопустимое имя для короткой ссылки"
    GENERATE_FAIL_MSG = "Не удалось сгенерировать уникальный short_id"

    id = db.Column(db.Integer, primary_key=True)
    original = db.Column(db.Text, nullable=False)
    short = db.Column(
        db.String(MAX_LENGHT_SHORT_LINK),
        unique=True,
        index=True,
        nullable=False,
    )
    timestamp = db.Column(
        db.DateTime, index=True, default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        """Преобразует объект модели в словарь для сериализации."""
        return dict(
            id=self.id,
            original=self.original,
            short=self.short,
            timestamp=self.timestamp,
        )

    def from_dict(self, data):
        """Заполняет поля объекта из словаря."""
        if "original" in data:
            self.original = data["original"]
        if "short" in data:
            self.short = data["short"]
        return self

    @classmethod
    def get(cls, short: str) -> "URLMap":
        """
        Возвращает объект по короткому коду.

        Если не найден — бросает ModelValidationError(404).
        """
        obj = cls.query.filter_by(short=short).first()
        if obj is None:
            raise ModelValidationError(
                "Указанный id не найден",
                status_code=404
            )
        return obj

    @staticmethod
    def _normalize_short(value: Optional[str]) -> str:
        """Нормализует значение короткой ссылки."""
        return (value or "").strip()

    @staticmethod
    def _raise_short_exists() -> None:
        """Выбрасывает исключение о существующей короткой ссылке."""
        raise ModelValidationError(URLMap.SHORT_EXISTS_MSG)

    @staticmethod
    def _validate_short(
        short: str, reserved_set: set, short_re=SHORT_RE
    ) -> None:
        """
        Валидирует короткую ссылку на соответствие формату.

        А также резервированным значениям.
        """
        if not short_re.fullmatch(short):
            raise ModelValidationError(URLMap.INVALID_SHORT_MSG)
        if short.lower() in reserved_set:
            URLMap._raise_short_exists()

    @staticmethod
    def _is_taken(short: str, exclude_id: Optional[int] = None) -> bool:
        """Проверяет, занята ли короткая ссылка другим объектом."""
        obj = URLMap.query.filter_by(short=short).first()
        return bool(obj and obj.id != exclude_id)

    @staticmethod
    def _try_commit() -> bool:
        """Пытается закоммитить транзакцию, обрабатывая ошибки целостности."""
        try:
            db.session.commit()
            return True
        except IntegrityError:
            db.session.rollback()
            return False

    
    @staticmethod
    def _random_short(length: int, alphabet: str = ALPHABET) -> str:
        """Генерирует случайную строку заданной длины из символов алфавита."""
        return "".join(choice(ALPHABET) for _ in range(length))


    @classmethod
    def generate_unique_short(
        cls,
        length: int = SHORT_AUTO_GENERATE_LENGTH,
        max_tries: int = MAX_TRIES,
    ) -> str:
        """Сгенерировать один случайный короткий код длиной length."""
        return cls._random_short(length)

    def _generate_and_commit(
        self,
        generate_short: Callable[[], str],
        attempts: int,
        reserved_set: set,
    ) -> None:
        """
        Коммит с повторами при коллизиях уникального индекса.

        Не делает предварительных проверок в БД — опирается на уникальный
        индекс.
        """
        for _ in range(max(1, attempts)):
            code = generate_short()
            if code.lower() in reserved_set:
                continue
            self.short = code
            db.session.add(self)
            if URLMap._try_commit():
                return
        raise ModelValidationError(URLMap.GENERATE_FAIL_MSG, status_code=500)

    def save(
        self,
        *,
        generate_short: Optional[Callable[[], str]] = None,
        reserved_shorts: Optional[Iterable[str]] = None,
        short_re=SHORT_RE,
        attempts: int = MAX_TRIES,
    ) -> "URLMap":
        """
        Сохраняет объект URLMap в БД с валидацией и обработкой коротких ссылок.

        1) Если короткая ссылка указана явно — валидирует формат и
           уникальность, сохраняет, при конфликте отдаёт SHORT_EXISTS_MSG.
        2) Если короткая ссылка не указана — генерирует код и пытается
           закоммитить (повторы attempts раз при коллизиях).
        """
        reserved_set = set(reserved_shorts or [])
        short = URLMap._normalize_short(self.short)
        if short:
            URLMap._validate_short(short, reserved_set, short_re)
            if URLMap._is_taken(short, exclude_id=self.id):
                URLMap._raise_short_exists()
            self.short = short
            db.session.add(self)
            if not URLMap._try_commit():
                URLMap._raise_short_exists()
            return self
        if generate_short is None:
            raise ModelValidationError(
                URLMap.GENERATE_FAIL_MSG,
                status_code=500
            )
        self._generate_and_commit(generate_short, attempts, reserved_set)
        return self