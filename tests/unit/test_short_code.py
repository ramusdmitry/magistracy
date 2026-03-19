"""Юнит-тесты: генерация и валидация коротких ссылок."""
import pytest

from app.services.link_service import generate_short_code, is_valid_short_code


class TestGenerateShortCode:
    """Тесты генерации уникального короткого кода."""

    def test_returns_string_of_default_length(self):
        code = generate_short_code()
        assert isinstance(code, str)
        assert len(code) == 6

    def test_returns_custom_length(self):
        code = generate_short_code(length=10)
        assert len(code) == 10

    def test_contains_only_alphanumeric(self):
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        for _ in range(20):
            code = generate_short_code()
            assert all(c in alphabet for c in code)

    def test_generates_different_codes(self):
        codes = {generate_short_code() for _ in range(100)}
        assert len(codes) == 100


class TestIsValidShortCode:
    """Тесты валидации формата short_code."""

    def test_valid_simple(self):
        assert is_valid_short_code("abc") is True
        assert is_valid_short_code("ABC123") is True

    def test_valid_with_underscore_and_dash(self):
        assert is_valid_short_code("a-b_c") is True
        assert is_valid_short_code("my_link") is True

    def test_invalid_empty(self):
        assert is_valid_short_code("") is False

    def test_invalid_special_chars(self):
        assert is_valid_short_code("a!b") is False
        assert is_valid_short_code("a b") is False
        assert is_valid_short_code("a@b") is False

    def test_invalid_too_long(self):
        assert is_valid_short_code("a" * 51) is False

    def test_valid_max_length(self):
        assert is_valid_short_code("a" * 50) is True
