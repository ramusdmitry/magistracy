from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_db, init_db
from app.routers import auth, links

app = FastAPI(
    title="Сервис сокращения ссылок",
    description="API для создания, управления и аналитики коротких ссылок",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(links.router, prefix="/links", tags=["links"])


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return {"message": "Сервис сокращения ссылок", "docs": "/docs"}
