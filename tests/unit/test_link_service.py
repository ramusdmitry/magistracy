"""Юнит-тесты: логика LinkService."""
import pytest

from app.services.link_service import LinkService, is_valid_short_code


class TestLinkServiceShorten:
    """Тесты создания коротких ссылок."""

    def test_invalid_custom_alias_special_chars(self, db_session):
        """Недопустимые символы в custom_alias."""
        service = LinkService(db_session)
        with pytest.raises(ValueError, match="Недопустимый формат"):
            service.shorten("https://example.com", custom_alias="invalid!")

    def test_invalid_custom_alias_empty(self, db_session):
        """Пустой alias не проходит валидацию (если передать пустую строку)."""
        # Пустая строка — falsy, идёт ветка auto-generate, но is_valid_short_code("") = False
        assert is_valid_short_code("") is False

    def test_invalid_custom_alias_spaces(self, db_session):
        """Пробелы в alias недопустимы."""
        service = LinkService(db_session)
        with pytest.raises(ValueError, match="Недопустимый формат"):
            service.shorten("https://example.com", custom_alias="has space")
