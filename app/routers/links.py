from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.link import LinkShortenRequest, LinkResponse, LinkStats, LinkUpdate
from app.services.link_service import LinkService
from app.routers.auth import get_current_user_optional, get_current_user_required
from app.models.user import User

router = APIRouter()


def _get_link_response(link) -> LinkResponse:
    return LinkResponse(
        id=link.id,
        short_code=link.short_code,
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        project_name=link.project_name,
    )


@router.get("/search", response_model=list)
def search_by_url(
    original_url: str,
    db: Session = Depends(get_db),
):
    service = LinkService(db)
    links = service.search_by_url(original_url)
    return [_get_link_response(l) for l in links]


@router.get("/expired/history", response_model=list)
def list_expired_links(db: Session = Depends(get_db)):
    service = LinkService(db)
    links = service.get_expired_links()
    return [
        {
            "short_code": l.short_code,
            "original_url": l.original_url,
            "created_at": l.created_at,
            "expired_at": l.expired_at,
            "click_count": l.click_count,
        }
        for l in links
    ]


@router.delete("/cleanup/unused")
def cleanup_unused_links(
    days: int = 30,
    db: Session = Depends(get_db),
):
    service = LinkService(db)
    count = service.cleanup_unused(days)
    return {"status": "ok", "deleted_count": count}


@router.post("/shorten", response_model=LinkResponse)
def shorten_link(
    request: LinkShortenRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    service = LinkService(db)
    try:
        link = service.shorten(
            original_url=request.original_url,
            custom_alias=request.custom_alias,
            expires_at=request.expires_at,
            project_name=request.project_name,
            user_id=current_user.id if current_user else None,
        )
        return _get_link_response(link)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{short_code}")
def redirect_to_url(
    short_code: str,
    db: Session = Depends(get_db),
):
    service = LinkService(db)
    url = service.redirect(short_code)
    if not url:
        raise HTTPException(status_code=404, detail="Ссылка не найдена или истекла")
    return RedirectResponse(url=url, status_code=302)


@router.put("/{short_code}", response_model=LinkResponse)
def update_link(
    short_code: str,
    request: LinkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    service = LinkService(db)
    link = service.update(short_code, request.original_url, current_user.id)
    if not link:
        raise HTTPException(status_code=404, detail="Ссылка не найдена или нет прав")
    return _get_link_response(link)


@router.delete("/{short_code}")
def delete_link(
    short_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    service = LinkService(db)
    ok = service.delete(short_code, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Ссылка не найдена или нет прав")
    return {"status": "ok", "message": "Ссылка удалена"}


@router.get("/{short_code}/stats", response_model=LinkStats)
def get_link_stats(
    short_code: str,
    db: Session = Depends(get_db),
):
    service = LinkService(db)
    link = service.get_stats(short_code)
    if not link:
        raise HTTPException(status_code=404, detail="Ссылка не найдена или истекла")
    return LinkStats(
        short_code=link.short_code,
        original_url=link.original_url,
        created_at=link.created_at,
        click_count=link.click_count,
        last_used_at=link.last_used_at,
        expires_at=link.expires_at,
    )
