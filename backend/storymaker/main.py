from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import api_router, install_error_handlers
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


def create_app() -> FastAPI:
    app = FastAPI(title="StoryMaker", lifespan=lifespan)
    install_error_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
    return app


app = create_app()
