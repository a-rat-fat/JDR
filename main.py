import os, uuid
from typing import Dict, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import SQLModel, Field, create_engine, Session, select
from starlette.websockets import WebSocketState

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
PGSSLMODE = os.getenv("PGSSLMODE", "").strip().lower()

if DATABASE_URL and "sslmode=" not in DATABASE_URL and PGSSLMODE=="require":
    DATABASE_URL += ("&" if "?" in DATABASE_URL else "?") + "sslmode=require"

engine = create_engine(DATABASE_URL or "sqlite:///./app.db", echo=False)

class Marker(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    seed: str
    x: int
    y: int
    label: str
    color: str
    type: str = "lieu"
    notes: str = ""

def init_db():
    SQLModel.metadata.create_all(engine)

app = FastAPI(title="JDR Map (FastAPI)")
app.mount("/public", StaticFiles(directory="public"), name="public")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def root():
    return FileResponse("public/index.html")

@app.get("/api/health")
def health():
    return {"ok": True, "db": bool(DATABASE_URL)}

class MarkerIn(BaseModel):
    seed: str
    x: int
    y: int
    label: str
    color: str
    type: str = "lieu"
    notes: str = ""

@app.get("/api/markers")
def list_markers(seed: str):
    with Session(engine) as session:
        rows = session.exec(select(Marker).where(Marker.seed==seed).order_by(Marker.id)).all()
        return {"markers":[m.model_dump() for m in rows]}

@app.post("/api/markers")
def create_marker(m: MarkerIn):
    rec = Marker(**m.model_dump())
    with Session(engine) as session:
        session.add(rec); session.commit(); session.refresh(rec)
    RoomManager.broadcast(m.seed, {"op":"added","marker":rec.model_dump()})
    return {"saved": True, "id": str(rec.id)}

@app.delete("/api/markers/{mid}")
def delete_marker(mid: str, seed: str):
    with Session(engine) as session:
        obj = session.get(Marker, uuid.UUID(mid))
        if obj and obj.seed == seed:
            session.delete(obj); session.commit()
            RoomManager.broadcast(seed, {"op":"removed","id": mid})
            return {"ok": True}
    return JSONResponse({"ok": False}, status_code=404)

class RoomManager:
    rooms: Dict[str, Set[WebSocket]] = {}

    @classmethod
    async def join(cls, seed: str, ws: WebSocket):
        await ws.accept()
        cls.rooms.setdefault(seed, set()).add(ws)

    @classmethod
    def leave(cls, seed: str, ws: WebSocket):
        if seed in cls.rooms and ws in cls.rooms[seed]:
            cls.rooms[seed].remove(ws)
            if not cls.rooms[seed]: del cls.rooms[seed]

    @classmethod
    def broadcast(cls, seed: str, message: dict):
        if seed not in cls.rooms: return
        dead = []
        for ws in list(cls.rooms[seed]):
            try:
                if ws.application_state.value == 3:  # DISCONNECTED
                    dead.append(ws); continue
                import anyio
                anyio.from_thread.run(awaitable=ws.send_json, data=message)
            except Exception:
                dead.append(ws)
        for ws in dead: cls.leave(seed, ws)

@app.websocket("/ws/{seed}")
async def ws_seed(ws: WebSocket, seed: str):
    await RoomManager.join(seed, ws)
    try:
        with Session(engine) as session:
            rows = session.exec(select(Marker).where(Marker.seed==seed).order_by(Marker.id)).all()
            await ws.send_json({"op":"snapshot","markers":[m.model_dump() for m in rows]})
        while True:
            data = await ws.receive_json()
            if data.get("op")=="add":
                m = data["marker"]
                rec = Marker(**m)
                with Session(engine) as session:
                    session.add(rec); session.commit(); session.refresh(rec)
                await ws.send_json({"op":"added","marker":rec.model_dump()})
                RoomManager.broadcast(seed, {"op":"added","marker":rec.model_dump()})
            elif data.get("op")=="remove":
                mid = data.get("id")
                with Session(engine) as session:
                    obj = session.get(Marker, uuid.UUID(mid))
                    if obj and obj.seed==seed:
                        session.delete(obj); session.commit()
                        await ws.send_json({"op":"removed","id": mid})
                        RoomManager.broadcast(seed, {"op":"removed","id": mid})
    except WebSocketDisconnect:
        RoomManager.leave(seed, ws)
    except Exception:
        RoomManager.leave(seed, ws)
