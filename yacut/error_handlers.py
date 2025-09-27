from flask import jsonify, render_template

from . import app


class InvalidAPIUsageError(Exception):
    """
    Кастомный класс исключения для обработки ошибок API.

    Позволяет задавать сообщение об ошибке и HTTP статус код.
    """

    status_code = 400

    def __init__(self, message, status_code=None):
        """Инициализирует исключение с сообщением и статус кодом."""
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self):
        """Преобразует исключение в словарь для JSON-сериализации."""
        return dict(message=self.message)


@app.errorhandler(InvalidAPIUsageError)
def handle_invalid_api_usage(error):
    """
    Обработчик кастомных исключений API.

    Возвращает JSON-ответ с сообщением об ошибке и соответствующим
    статус кодом.
    """
    return jsonify({'message': error.message}), error.status_code


@app.errorhandler(404)
def page_not_found(e):
    """
    Обработчик ошибки 404 - Страница не найдена.

    Возвращает кастомную HTML-страницу для ошибки 404.
    """
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(e):
    """
    Обработчик ошибки 500 - Внутренняя ошибка сервера.

    Возвращает кастомную HTML-страницу для ошибки 500.
    """
    return render_template('500.html'), 500