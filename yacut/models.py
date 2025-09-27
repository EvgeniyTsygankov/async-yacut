from datetime import datetime, timezone

from yacut import db


class URLMap(db.Model):
    """
    Модель для представления коротких ссылок в базе данных.

    Содержит оригинальные ссылки и их короткие идентификаторы.
    """

    id = db.Column(db.Integer, primary_key=True)
    original = db.Column(db.Text, nullable=False)
    short = db.Column(db.String(16), unique=True, index=True, nullable=False)
    timestamp = db.Column(
        db.DateTime, index=True, default=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self):
        """Преобразует объект модели в словарь для сериализации."""
        return dict(
            id=self.id,
            original=self.original,
            short=self.short,
            timestamp=self.timestamp
        )

    def from_dict(self, data):
        """Заполняет поля объекта из словаря."""
        for field in ['original', 'short']:
            if field in data:
                setattr(self, field, data[field])