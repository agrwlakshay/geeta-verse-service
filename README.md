# Geeta API (Neon + FastAPI)

## 1) Install
```bash
cd /Users/akshay.agarwal/Documents/Work/Geeta/bhagavad-gita/api
python3 -m pip install -r requirements.txt
```

## 2) Configure
```bash
cp .env.example .env
# edit .env with your Neon DATABASE_URL and API_KEY
```

## 3) Run
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 4) Test
```bash
curl -H 'x-api-key: YOUR_API_KEY' http://127.0.0.1:8000/chapters
curl -H 'x-api-key: YOUR_API_KEY' http://127.0.0.1:8000/verse/2/47
curl -H 'x-api-key: YOUR_API_KEY' 'http://127.0.0.1:8000/search?q=karma&limit=5'
```

## Endpoints
- `GET /health` (no auth)
- `GET /chapters`
- `GET /chapter/{chapter_id}`
- `GET /verse/{chapter_id}/{verse_number}`
- `GET /search?q=...&limit=20`

Auth header for protected endpoints:
- `x-api-key: <API_KEY>`
