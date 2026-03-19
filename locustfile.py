"""
Нагрузочное тестирование сервиса сокращения ссылок.

Запуск:
  locust -f locustfile.py --host=http://localhost:8000

Сервер должен быть запущен (uvicorn app.main:app).

Результаты: веб-интерфейс на http://localhost:8089 или отчёт в консоль:
  locust -f locustfile.py --host=http://localhost:8000 --headless -u 10 -r 2 -t 30s
"""
import random
import string

from locust import HttpUser, task, between


def random_url():
    """Случайный URL для создания ссылки."""
    path = "".join(random.choices(string.ascii_lowercase, k=8))
    return f"https://example.com/{path}"


def random_alias():
    """Случайный alias (уникальный для избежания коллизий)."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


class LinkShortenerUser(HttpUser):
    """Пользователь: создание ссылок, редиректы, статистика."""

    wait_time = between(0.5, 1.5)

    def on_start(self):
        """При старте создаём одну ссылку для последующих редиректов."""
        r = self.client.post(
            "/links/shorten",
            json={"original_url": random_url(), "custom_alias": f"load_{random_alias()}"},
        )
        if r.status_code == 200:
            self.short_code = r.json().get("short_code")
        else:
            self.short_code = None

    @task(3)
    def create_link(self):
        """Массовое создание коротких ссылок."""
        self.client.post(
            "/links/shorten",
            json={
                "original_url": random_url(),
                "custom_alias": f"load_{random_alias()}",
            },
        )

    @task(5)
    def redirect(self):
        """Редирект — проверка влияния кэширования при повторных запросах."""
        if self.short_code:
            self.client.get(f"/links/{self.short_code}", allow_redirects=False)

    @task(1)
    def get_stats(self):
        """Получение статистики."""
        if self.short_code:
            self.client.get(f"/links/{self.short_code}/stats")


class RedirectHeavyUser(HttpUser):
    """
    Пользователь с упором на редиректы.
    Оценивает влияние кэша: повторные запросы к одной ссылке должны быть быстрее.
    """

    wait_time = between(0.1, 0.3)

    def on_start(self):
        r = self.client.post(
            "/links/shorten",
            json={"original_url": "https://cache-test.com", "custom_alias": f"cache_{random_alias()}"},
        )
        self.short_code = r.json().get("short_code") if r.status_code == 200 else None

    @task
    def redirect_repeated(self):
        """Многократные редиректы к одной ссылке (прогрев кэша)."""
        if self.short_code:
            self.client.get(f"/links/{self.short_code}", allow_redirects=False)
