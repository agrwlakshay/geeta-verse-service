# Geeta Verse Service

## What We Are Building
This project provides an API for Bhagavad Gita data so cloud AI agents and apps can query verses, chapters, and commentary in a controlled way.

The goal is:
- Keep the source of truth in Neon Postgres.
- Expose a stable HTTP interface for consumers.
- Protect access with an API key (`x-api-key`).
- Support common queries like chapter listing, verse lookup, and text search.

## Data Model (High Level)
- `chapters`: chapter metadata (name, translation, summaries).
- `verses`: core verse fields (`chapter_id`, `verse_number`, `speaker`, `slok`, `transliteration`).
- `commentaries`: commentary by source key per verse.

## Authentication
All data endpoints require:
- Header: `x-api-key: <YOUR_API_KEY>`

`/health` is public.

## Base URLs
- Local: `http://127.0.0.1:8000`
- Production (example): `https://geeta-verse-service-production.up.railway.app`

## Endpoints
- `GET /health`
- `GET /chapters`
- `GET /chapter/{chapter_id}`
- `GET /verse/{chapter_id}/{verse_number}`
- `GET /search?q=<text>&limit=<n>`

## Example Requests

### 1) Health
```bash
curl http://127.0.0.1:8000/health
```

### 2) List chapters
```bash
curl -H "x-api-key: YOUR_API_KEY" \
  http://127.0.0.1:8000/chapters
```

### 3) Get one chapter
```bash
curl -H "x-api-key: YOUR_API_KEY" \
  http://127.0.0.1:8000/chapter/2
```

### 4) Get one verse with commentaries
```bash
curl -H "x-api-key: YOUR_API_KEY" \
  http://127.0.0.1:8000/verse/2/47
```

### 5) Search verses
```bash
curl -H "x-api-key: YOUR_API_KEY" \
  "http://127.0.0.1:8000/search?q=karma&limit=5"
```

### 6) Production request example
```bash
curl -H "x-api-key: YOUR_API_KEY" \
  https://geeta-verse-service-production.up.railway.app/chapters
```

## Local Run
```bash
python3 -m pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Environment Variables
Create `.env` in this folder:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require
API_KEY=your-strong-random-key
PORT=8000
```

## Notes
- Rotate API keys if exposed.
- Keep `DATABASE_URL` and `API_KEY` out of source control.
- Prefer Neon pooled connection string in production.
