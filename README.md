# JDR – FastAPI + WebSocket + Postgres (Railway/OrbStack)

Stack Python :
- **FastAPI + WebSocket** (multijoueur par seed)
- **SQLModel/SQLAlchemy + Postgres** (persistance). Sans `DATABASE_URL`, fallback en **SQLite** (app.db).
- **Docker** prêt pour OrbStack et Railway (Hobby).

## Local sans Docker
```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
./start.sh
# http://localhost:3000
```

## OrbStack / Docker
```bash
docker build -t jdr-fastapi .
docker run -p 3000:3000 --env-file .env jdr-fastapi
```
`.env` exemple :
```
PORT=3000
DATABASE_URL=postgresql://user:pass@host:5432/dbname
PGSSLMODE=require
```

## Railway (Hobby)
1. Deploy from Repo (ou Upload du dossier).
2. Add Plugin **PostgreSQL** → `DATABASE_URL` auto.
3. Variables : `PGSSLMODE=require` (souvent nécessaire).
4. Start command: `./start.sh`

## Endpoints
- `GET /api/health` → `{ ok, db }`
- `GET /api/markers?seed=XYZ`
- `POST /api/markers` JSON `{ seed, x, y, label, color, type, notes }`
- `DELETE /api/markers/{id}?seed=XYZ`

## WebSocket
- `ws(s)://HOST/ws/{seed}`
- Server → Client: `snapshot`, `added`, `removed`
- Client → Server: `{"op":"add","marker":...}`, `{"op":"remove","id":"..."}`

> Pour production multi-réplicas, prévoir Redis Pub/Sub pour propager les messages WS entre instances.
