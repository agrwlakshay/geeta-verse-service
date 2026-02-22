from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from psycopg import Error as PsycopgError
from psycopg.errors import UndefinedTable
from psycopg_pool import ConnectionPool
#random comment
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


def ensure_user_preferences_table() -> None:
    assert pool is not None
    sql = """
    CREATE TABLE IF NOT EXISTS user_preferences (
        chat_id BIGINT PRIMARY KEY,
        source TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    pool = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=10)
    try:
        ensure_user_preferences_table()
        yield
    finally:
        if pool is not None:
            pool.close()


app = FastAPI(title="Geeta API", version="1.0.0", lifespan=lifespan)


class PreferenceUpdate(BaseModel):
    source: str = Field(min_length=1, max_length=64)


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


def get_verse_row(chapter_id: int, verse_number: int) -> dict[str, Any]:
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
    return verse_row


def get_commentary_rows(verse_id: str) -> list[dict[str, Any]]:
    return fetch_all_dicts(
        """
        SELECT source_key, author, et, ht, ec, hc, sc
        FROM commentaries
        WHERE verse_id = %s
        ORDER BY source_key
        """,
        (verse_id,),
    )


def get_commentary_sources(verse_id: str) -> list[dict[str, Any]]:
    return fetch_all_dicts(
        """
        SELECT
            source_key,
            author,
            (et IS NOT NULL AND et <> '') AS has_et,
            (ht IS NOT NULL AND ht <> '') AS has_ht,
            (ec IS NOT NULL AND ec <> '') AS has_ec,
            (hc IS NOT NULL AND hc <> '') AS has_hc,
            (sc IS NOT NULL AND sc <> '') AS has_sc
        FROM commentaries
        WHERE verse_id = %s
        ORDER BY source_key
        """,
        (verse_id,),
    )


def get_single_clean_commentary(verse_id: str, source: str | None) -> dict[str, Any] | None:
    if source:
        row = fetch_one_dict(
            """
            SELECT
                source_key,
                author,
                COALESCE(
                    NULLIF(et, ''),
                    NULLIF(ht, ''),
                    NULLIF(ec, ''),
                    NULLIF(hc, ''),
                    NULLIF(sc, '')
                ) AS text
            FROM commentaries
            WHERE verse_id = %s AND source_key = %s
            """,
            (verse_id, source),
        )
        if row:
            return row

    return fetch_one_dict(
        """
        SELECT
            source_key,
            author,
            COALESCE(
                NULLIF(et, ''),
                NULLIF(ht, ''),
                NULLIF(ec, ''),
                NULLIF(hc, ''),
                NULLIF(sc, '')
            ) AS text
        FROM commentaries
        WHERE verse_id = %s
        ORDER BY source_key
        LIMIT 1
        """,
        (verse_id,),
    )


def first_commentary_text(row: dict[str, Any]) -> str | None:
    for key in ("et", "ht", "ec", "hc", "sc"):
        value = row.get(key)
        if value:
            return str(value)
    return None


def get_user_preference(chat_id: int) -> dict[str, Any] | None:
    return fetch_one_dict(
        """
        SELECT chat_id, source, updated_at
        FROM user_preferences
        WHERE chat_id = %s
        """,
        (chat_id,),
    )


def upsert_user_preference(chat_id: int, source: str) -> dict[str, Any]:
    source = source.strip().lower()
    if not source:
        raise HTTPException(status_code=400, detail="Invalid source")

    assert pool is not None
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO user_preferences (chat_id, source, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (chat_id) DO UPDATE SET
                        source = EXCLUDED.source,
                        updated_at = NOW()
                    RETURNING chat_id, source, updated_at
                    """,
                    (chat_id, source),
                )
                row = cur.fetchone()
            conn.commit()
        return row
    except PsycopgError as exc:
        logger.exception("Postgres error during preference upsert: %s", exc)
        raise HTTPException(status_code=500, detail=f"Database query failed: {exc.__class__.__name__}") from exc


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


@app.get("/users/{chat_id}/preference", dependencies=[Depends(auth)])
def user_preference(chat_id: int) -> dict[str, Any]:
    pref = get_user_preference(chat_id)
    if not pref:
        return {"chat_id": chat_id, "source": None}
    return pref


@app.put("/users/{chat_id}/preference", dependencies=[Depends(auth)])
def set_user_preference(chat_id: int, payload: PreferenceUpdate) -> dict[str, Any]:
    return upsert_user_preference(chat_id, payload.source)


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
    verse_row = get_verse_row(chapter_id, verse_number)
    commentary_rows = get_commentary_rows(verse_row["id"])
    verse_row["commentaries"] = commentary_rows
    return verse_row


@app.get("/verse/{chapter_id}/{verse_number}/sources", dependencies=[Depends(auth)])
def verse_sources(chapter_id: int, verse_number: int) -> dict[str, Any]:
    verse_row = get_verse_row(chapter_id, verse_number)
    commentary_rows = get_commentary_sources(verse_row["id"])
    sources = []
    for row in commentary_rows:
        available = []
        if row.get("has_et"):
            available.append("et")
        if row.get("has_ht"):
            available.append("ht")
        if row.get("has_ec"):
            available.append("ec")
        if row.get("has_hc"):
            available.append("hc")
        if row.get("has_sc"):
            available.append("sc")
        sources.append(
            {
                "source_key": row["source_key"],
                "author": row.get("author"),
                "available_fields": available,
            }
        )
    return {
        "verse_id": verse_row["id"],
        "chapter_id": verse_row["chapter_id"],
        "verse_number": verse_row["verse_number"],
        "default_source": sources[0]["source_key"] if sources else None,
        "sources": sources,
    }


@app.get("/verse/{chapter_id}/{verse_number}/clean", dependencies=[Depends(auth)])
def verse_clean(
    chapter_id: int,
    verse_number: int,
    source: str | None = Query(None, description="Preferred commentary source key, e.g. prabhu"),
) -> dict[str, Any]:
    verse_row = get_verse_row(chapter_id, verse_number)
    chosen = get_single_clean_commentary(verse_row["id"], source)
    commentary_text = chosen.get("text") if chosen else None
    return {
        "verse_id": verse_row["id"],
        "chapter_id": verse_row["chapter_id"],
        "verse_number": verse_row["verse_number"],
        "speaker": verse_row.get("speaker"),
        "slok": verse_row.get("slok"),
        "transliteration": verse_row.get("transliteration"),
        "commentary": {
            "source_key": chosen.get("source_key") if chosen else None,
            "author": chosen.get("author") if chosen else None,
            "text": commentary_text,
        },
    }


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
