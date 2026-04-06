import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import MAX_FILE_SIZE, ALLOWED_CONTENT_TYPES, DATABASE_URL
from app.database import init_db, Base
import app.database as db_module
from app.llm_service import (
    analyze_presentation,
    improve_presentation,
    imitate_presentation,
    compute_file_hash,
)
from app.models import Analysis

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize DB tables."""
    if DATABASE_URL:
        init_db()
        async with db_module.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized")
    else:
        logger.warning("DATABASE_URL not set — running without database")
    yield


app = FastAPI(title="SlideWise", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"{request.method} {request.url.path} - {response.status_code} ({duration:.2f}s)")
    return response


def get_session_id(request: Request) -> str:
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id


def set_session_cookie(response: JSONResponse, session_id: str) -> JSONResponse:
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=31536000)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    session_id = get_session_id(request)
    response = HTMLResponse(content=open("app/static/index.html", "r").read())
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=31536000)
    return response


@app.post("/analyze")
async def analyze(request: Request, file: UploadFile = File(...)):
    """Primary analysis: upload PDF, get full presentation feedback."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        result = await analyze_presentation(file_bytes)
    except ValueError as e:
        if "not configured" in str(e):
            return JSONResponse(status_code=500, content={"error": "LLM not configured"})
        return JSONResponse(status_code=502, content={"error": str(e)})
    except RuntimeError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in analyze: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

    session_id = get_session_id(request)
    response = JSONResponse(content=result)
    return set_session_cookie(response, session_id)


@app.post("/improve")
async def improve(
    request: Request,
    file: UploadFile = File(...),
    priority: str = Form(None),
    reference_file: UploadFile = File(None),
):
    """Improve presentation: by aspect or by reference."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    try:
        if reference_file:
            # Imitate mode: two PDFs
            ref_bytes = await reference_file.read()
            result = await imitate_presentation(file_bytes, ref_bytes)
        elif priority:
            result = await improve_presentation(file_bytes, priority)
        else:
            raise HTTPException(status_code=400, detail="Either priority or reference_file required")
    except ValueError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    except RuntimeError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in improve: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

    session_id = get_session_id(request)
    response = JSONResponse(content=result)
    return set_session_cookie(response, session_id)


@app.post("/save")
async def save_result(
    request: Request,
    presentation_hash: str = Form(...),
    original_feedback: str = Form(...),
    improved_feedback: str = Form(None),
    priority: str = Form(None),
    reference_presentation_hash: str = Form(None),
):
    """Save analysis result to database."""
    if not DATABASE_URL:
        return JSONResponse(status_code=501, content={"error": "Database not available"})

    session_id = get_session_id(request)

    try:
        async with db_module.async_session() as db:
            record = Analysis(
                session_id=session_id,
                presentation_hash=presentation_hash,
                original_feedback=original_feedback,
                improved_feedback=improved_feedback,
                priority=priority,
                reference_presentation_hash=reference_presentation_hash,
            )
            db.add(record)
            await db.commit()
            response = JSONResponse(content={"id": record.id})
            return set_session_cookie(response, session_id)
    except Exception as e:
        logger.error(f"Error saving result: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Failed to save"})


@app.get("/history")
async def history(request: Request):
    """Return last 10 analyses for the current session."""
    if not DATABASE_URL:
        return JSONResponse(status_code=501, content={"error": "History not available"})

    session_id = get_session_id(request)

    try:
        async with db_module.async_session() as db:
            stmt = (
                select(Analysis)
                .where(Analysis.session_id == session_id)
                .order_by(Analysis.created_at.desc())
                .limit(10)
            )
            result = await db.execute(stmt)
            records = result.scalars().all()

        items = [r.to_dict() for r in records]
        response = JSONResponse(content={"history": items})
        return set_session_cookie(response, session_id)
    except Exception as e:
        logger.error(f"Error fetching history: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Failed to fetch history"})
