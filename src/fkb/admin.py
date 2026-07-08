from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import knowledge_root_for_owner, load_config
from .indexer import index_owner
from .search import search_text

app = FastAPI(title="Filesystem Knowledge Bridge Admin")


class SearchRequest(BaseModel):
    query: str
    top_k: int | None = None


def current_user(x_authentik_username: str | None) -> str:
    cfg = load_config()
    if cfg.admin.allow_header_auth and x_authentik_username:
        return x_authentik_username
    return cfg.knowledge.owner


@app.get("/")
def root():
    return {
        "service": "filesystem-knowledge-bridge",
        "endpoints": ["GET /me/status", "POST /me/index", "POST /me/search"],
    }


@app.get("/me/status")
def my_status(x_authentik_username: str | None = Header(default=None)):
    cfg = load_config()
    user = current_user(x_authentik_username)
    path = knowledge_root_for_owner(cfg, user)
    return {"user": user, "knowledge_root": str(path), "exists": path.exists()}


@app.post("/me/index")
def index_my_knowledge(x_authentik_username: str | None = Header(default=None)):
    user = current_user(x_authentik_username)
    try:
        index_owner(user)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"user": user, "status": "indexed"}


@app.post("/me/search")
def search_my_knowledge(body: SearchRequest, x_authentik_username: str | None = Header(default=None)):
    user = current_user(x_authentik_username)
    return {"user": user, "result": search_text(body.query, owner=user, top_k=body.top_k)}
