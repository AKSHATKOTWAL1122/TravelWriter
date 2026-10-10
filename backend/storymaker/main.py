from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import connect, run_migrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A failing migration raises here, which stops startup.
    conn = connect()
    try:
        run_migrations(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="StoryMaker", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
