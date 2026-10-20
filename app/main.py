import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.keitaro.client import KeitaroError
from app.services.creator import CreateError
from app.services.editor import Conflict, EditorError, NotFound

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Keitaro wrapper", version="0.1.0")
app.include_router(router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message})


@app.exception_handler(KeitaroError)
def keitaro_error(_: Request, exc: KeitaroError):
    status = 404 if exc.status_code == 404 else 502
    return _error(status, str(exc))


@app.exception_handler(NotFound)
def not_found(_: Request, exc: NotFound):
    return _error(404, str(exc))


@app.exception_handler(Conflict)
def conflict(_: Request, exc: Conflict):
    return _error(409, str(exc))


@app.exception_handler(EditorError)
@app.exception_handler(CreateError)
def bad_request(_: Request, exc: ValueError):
    return _error(400, str(exc))
