from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.services.auth_service import AuthService, create_access_token, decode_token
from app.schemas.user import UserCreate, UserResponse, Token
from app.models.user import User

router = APIRouter()
security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    payload = decode_token(credentials.credentials)
    if not payload or "sub" not in payload:
        return None
    user_id = int(payload["sub"])
    svc = AuthService(db)
    return svc.get_user_by_id(user_id)


def get_current_user_required(
    current_user: User | None = Depends(get_current_user_optional),
) -> User:
    if not current_user:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return current_user


@router.post("/register", response_model=UserResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    svc = AuthService(db)
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    user = svc.register(user_data)
    return UserResponse(id=user.id, username=user.username, email=user.email)


@router.post("/login", response_model=Token)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    svc = AuthService(db)
    user = svc.authenticate(data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Неверное имя или пароль")
    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token, token_type="bearer")
