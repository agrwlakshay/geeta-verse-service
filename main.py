from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from psycopg import Error as PsycopgError
from psycopg.errors import UndefinedTable
from psycopg_pool import ConnectionPool

load_dotenv()
logger = logging.getLogger("geeta_api")

DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.getenv("API_KEY")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")
if not API_KEY:
    raise RuntimeError("API_KEY is required")

pool: ConnectionPool | None = None
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def auth(api_key: str | None = Security(api_key_header)) -> None:
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    pool = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=10)
    try:
        yield
    finally:
        if pool is not None:
            pool.close()


app = FastAPI(title="Geeta API", version="1.0.0", lifespan=lifespan)


def fetch_all_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    assert pool is not None
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
    except UndefinedTable as exc:
        logger.exception("Undefined table during query")
        raise HTTPException(
            status_code=503,
            detail="Database schema not ready yet. Wait for import/migration to finish.",
        ) from exc
    except PsycopgError as exc:
        logger.exception("Postgres error during query: %s", exc)
        raise HTTPException(status_code=500, detail=f"Database query failed: {exc.__class__.__name__}") from exc


def fetch_one_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    assert pool is not None
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return cur.fetchone()
    except UndefinedTable as exc:
        logger.exception("Undefined table during query")
        raise HTTPException(
            status_code=503,
            detail="Database schema not ready yet. Wait for import/migration to finish.",
        ) from exc
    except PsycopgError as exc:
        logger.exception("Postgres error during query: %s", exc)
        raise HTTPException(status_code=500, detail=f"Database query failed: {exc.__class__.__name__}") from exc


# Imported here to keep imports grouped and explicit.
from psycopg.rows import dict_row  # noqa: E402


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/chapters", dependencies=[Depends(auth)])
def chapters() -> list[dict[str, Any]]:
    return fetch_all_dicts(
        """
        SELECT id, name, translation, transliteration, verses_count, meaning_en, meaning_hi
        FROM chapters
        ORDER BY id
        """
    )


@app.get("/chapter/{chapter_id}", dependencies=[Depends(auth)])
def chapter(chapter_id: int) -> dict[str, Any]:
    row = fetch_one_dict(
        """
        SELECT id, name, translation, transliteration, verses_count,
               meaning_en, meaning_hi, summary_en, summary_hi
        FROM chapters
        WHERE id = %s
        """,
        (chapter_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return row


@app.get("/verse/{chapter_id}/{verse_number}", dependencies=[Depends(auth)])
def verse(chapter_id: int, verse_number: int) -> dict[str, Any]:
    verse_row = fetch_one_dict(
        """
        SELECT id, chapter_id, verse_number, speaker, slok, transliteration
        FROM verses
        WHERE chapter_id = %s AND verse_number = %s
        """,
        (chapter_id, verse_number),
    )
    if not verse_row:
        raise HTTPException(status_code=404, detail="Verse not found")

    commentary_rows = fetch_all_dicts(
        """
        SELECT source_key, author, et, ht, ec, hc, sc
        FROM commentaries
        WHERE verse_id = %s
        ORDER BY source_key
        """,
        (verse_row["id"],),
    )
    verse_row["commentaries"] = commentary_rows
    return verse_row


@app.get("/search", dependencies=[Depends(auth)])
def search(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    like = f"%{q}%"
    return fetch_all_dicts(
        """
        SELECT id, chapter_id, verse_number, speaker, slok, transliteration
        FROM verses
        WHERE slok ILIKE %s OR transliteration ILIKE %s
        ORDER BY chapter_id, verse_number
        LIMIT %s
        """,
        (like, like, limit),
    )
