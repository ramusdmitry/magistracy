import re
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.cache import cache
from app.models.link import Link


def generate_short_code(length: int = 6) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def is_valid_short_code(code: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", code)) and 1 <= len(code) <= 50


class LinkService:
    REDIRECT_CACHE_TTL = 3600
    STATS_CACHE_TTL = 60
    SEARCH_CACHE_TTL = 120

    def __init__(self, db: Session):
        self.db = db

    def _invalidate_link_caches(self, short_code: str) -> None:
        cache.delete(f"redirect:{short_code}")
        cache.delete(f"stats:{short_code}")
        cache.delete_pattern("search:*")

    def shorten(
        self,
        original_url: str,
        custom_alias: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        project_name: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Link:
        if custom_alias:
            if not is_valid_short_code(custom_alias):
                raise ValueError("Недопустимый формат custom_alias")
            existing = self.db.query(Link).filter(
                Link.short_code == custom_alias,
                Link.is_expired == False,
            ).first()
            if existing:
                raise ValueError("Такой alias уже занят")
            short_code = custom_alias
        else:
            for _ in range(100):
                short_code = generate_short_code()
                if not self.db.query(Link).filter(
                    Link.short_code == short_code,
                    Link.is_expired == False,
                ).first():
                    break
            else:
                raise ValueError("Не удалось сгенерировать уникальный код")

        link = Link(
            short_code=short_code,
            original_url=original_url,
            expires_at=expires_at,
            project_name=project_name,
            created_by_user_id=user_id,
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    def get_by_short_code(self, short_code: str, use_cache: bool = True) -> Optional[Link]:
        if use_cache:
            cached_url = cache.get(f"redirect:{short_code}")
            if cached_url:
                link = self.db.query(Link).filter(
                    Link.short_code == short_code,
                    Link.is_expired == False,
                ).first()
                if link and link.original_url == cached_url:
                    if link.expires_at and datetime.utcnow() >= link.expires_at:
                        link.is_expired = True
                        link.expired_at = datetime.utcnow()
                        self.db.commit()
                        cache.delete(f"redirect:{short_code}")
                        return None
                    return link

        link = self.db.query(Link).filter(
            Link.short_code == short_code,
            Link.is_expired == False,
        ).first()
        if not link:
            return None

        if link.expires_at and datetime.utcnow() >= link.expires_at:
            link.is_expired = True
            link.expired_at = datetime.utcnow()
            self.db.commit()
            self._invalidate_link_caches(short_code)
            return None

        if use_cache:
            cache.set(f"redirect:{short_code}", link.original_url, self.REDIRECT_CACHE_TTL)
        return link

    def redirect(self, short_code: str) -> Optional[str]:
        link = self.get_by_short_code(short_code)
        if not link:
            return None
        link.click_count += 1
        link.last_used_at = datetime.utcnow()
        self.db.commit()
        self._invalidate_link_caches(short_code)
        return link.original_url

    def update(self, short_code: str, original_url: str, user_id: int) -> Optional[Link]:
        link = self.db.query(Link).filter(
            Link.short_code == short_code,
            Link.is_expired == False,
            Link.created_by_user_id == user_id,
        ).first()
        if not link:
            return None
        link.original_url = original_url
        self.db.commit()
        self.db.refresh(link)
        self._invalidate_link_caches(short_code)
        return link

    def delete(self, short_code: str, user_id: int) -> bool:
        link = self.db.query(Link).filter(
            Link.short_code == short_code,
            Link.created_by_user_id == user_id,
        ).first()
        if not link:
            return False
        link.is_expired = True
        link.expired_at = datetime.utcnow()
        self.db.commit()
        self._invalidate_link_caches(short_code)
        return True

    def get_stats(self, short_code: str, use_cache: bool = True) -> Optional[Link]:
        if use_cache:
            cached = cache.get(f"stats:{short_code}")
            if cached:
                link = self.db.query(Link).filter(
                    Link.short_code == short_code,
                    Link.is_expired == False,
                ).first()
                if link:
                    return link

        link = self.db.query(Link).filter(
            Link.short_code == short_code,
            Link.is_expired == False,
        ).first()
        if link:
            cache.set(f"stats:{short_code}", "1", self.STATS_CACHE_TTL)
        return link

    def search_by_url(self, original_url: str, use_cache: bool = True) -> List[Link]:
        cache_key = f"search:{original_url}"
        if use_cache:
            cached = cache.get_json(cache_key)
            if cached is not None and isinstance(cached, list):
                ids = cached
                links = self.db.query(Link).filter(
                    Link.id.in_(ids),
                    Link.is_expired == False,
                ).all()
                return links

        links = self.db.query(Link).filter(
            Link.original_url == original_url,
            Link.is_expired == False,
        ).all()
        if links:
            cache.set_json(cache_key, [l.id for l in links], self.SEARCH_CACHE_TTL)
        return links

    def get_expired_links(self) -> List[Link]:
        return self.db.query(Link).filter(Link.is_expired == True).order_by(
            Link.expired_at.desc()
        ).all()

    def cleanup_unused(self, days: int) -> int:
        threshold = datetime.utcnow() - timedelta(days=days)
        links = self.db.query(Link).filter(
            Link.is_expired == False,
            Link.last_used_at != None,
            Link.last_used_at < threshold,
        ).all()
        for link in links:
            link.is_expired = True
            link.expired_at = datetime.utcnow()
            self._invalidate_link_caches(link.short_code)
        self.db.commit()
        return len(links)
