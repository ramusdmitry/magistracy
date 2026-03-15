import json
from typing import Optional, List
import redis
from app.config import get_settings

_settings = get_settings()
_redis: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    global _redis
    if _redis is None:
        try:
            _redis = redis.from_url(_settings.REDIS_URL, decode_responses=True)
            _redis.ping()
        except Exception:
            _redis = False  # type: ignore
    return _redis if _redis else None


class Cache:
    def get(self, key: str) -> Optional[str]:
        try:
            return get_redis().get(key)
        except Exception:
            return None

    def set(self, key: str, value: str, ttl: int = 300) -> None:
        try:
            get_redis().set(key, value, ex=ttl)
        except Exception:
            pass

    def set_json(self, key: str, value: object, ttl: int = 300) -> None:
        self.set(key, json.dumps(value), ttl)

    def get_json(self, key: str) -> Optional[object]:
        val = self.get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return None

    def delete(self, key: str) -> None:
        try:
            get_redis().delete(key)
        except Exception:
            pass

    def delete_pattern(self, pattern: str) -> None:
        try:
            r = get_redis()
            keys = list(r.scan_iter(match=pattern))
            if keys:
                r.delete(*keys)
        except Exception:
            pass


cache = Cache()
