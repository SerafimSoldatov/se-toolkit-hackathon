import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import MAX_FILE_SIZE, ALLOWED_CONTENT_TYPES, DATABASE_URL
from app.database import init_db, Base, engine, async_session
from app.llm_service import analyze_slide, compute_file_hash
from app.models import Feedback

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    if DATABASE_URL:
        init_db()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized")
    else:
        logger.info("Running without database (Version 1 mode)")
    yield


app = FastAPI(title="SlideWise", lifespan=lifespan)


# Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next()
    duration = time.time() - start
    logger.info(f"{request.method} {request.url.path} - {response.status_code} ({duration:.2f}s)")
    return response


def get_session_id(request: Request) -> str:
    """Get or create session_id from cookie."""
    session_id = request.cookies.get("session_id")
    new_session = False
    if not session_id:
        session_id = str(uuid.uuid4())
        new_session = True
    return session_id, new_session


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the HTML frontend."""
    session_id, is_new_session = get_session_id(request)
    response = HTMLResponse(content=open("app/static/index.html", "r").read())
    if is_new_session:
        response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=31536000)
    return response


@app.post("/analyze")
async def analyze(request: Request, file: UploadFile = File(...)):
    """
    Accept an image/PDF file, analyze it via LLM, return JSON feedback.
    Optionally saves to database (V2).
    """
    # Validate content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only images (JPEG, PNG) and PDFs are supported",
        )

    # Read file content
    file_bytes = await file.read()

    # Validate file size
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File too large (max 5MB)",
        )

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Analyze via LLM
    try:
        result = await analyze_slide(file_bytes)
    except ValueError as e:
        if "not configured" in str(e):
            return JSONResponse(
                status_code=500,
                content={"error": "LLM not configured"},
            )
        return JSONResponse(
            status_code=502,
            content={"error": "Invalid response from AI"},
        )
    except TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"error": "Analysis taking too long"},
        )
    except RuntimeError:
        return JSONResponse(
            status_code=502,
            content={"error": "Invalid response from AI"},
        )
    except Exception as e:
        logger.error(f"Unexpected error in analyze: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    # Save to database (V2) — fire and forget, don't block response
    session_id, is_new_session = get_session_id(request)
    if DATABASE_URL:
        try:
            async with async_session() as db:
                image_hash = compute_file_hash(file_bytes)
                record = Feedback(
                    session_id=session_id,
                    image_hash=image_hash,
                    content_feedback=result.get("content", ""),
                    design_feedback=result.get("design", ""),
                    tips=json.dumps(result.get("tips", [])),
                )
                db.add(record)
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to save feedback to DB: {e}")

    response = JSONResponse(content=result)
    response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=31536000)
    return response


@app.get("/history")
async def history(request: Request):
    """Return last 5 analyses for the current session (V2)."""
    if not DATABASE_URL:
        return JSONResponse(status_code=501, content={"error": "History not available"})

    session_id, is_new_session = get_session_id(request)

    try:
        async with async_session() as db:
            stmt = (
                select(Feedback)
                .where(Feedback.session_id == session_id)
                .order_by(Feedback.created_at.desc())
                .limit(5)
            )
            result = await db.execute(stmt)
            records = result.scalars().all()

        items = []
        for r in records:
            items.append({
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "content_preview": r.content_feedback[:100] + "..." if len(r.content_feedback) > 100 else r.content_feedback,
                "content": r.content_feedback,
                "design": r.design_feedback,
                "tips": json.loads(r.tips) if r.tips else [],
            })

        response = JSONResponse(content={"history": items})
        response.set_cookie(key="session_id", value=session_id, httponly=True, samesite="lax", max_age=31536000)
        return response
    except Exception as e:
        logger.error(f"Error fetching history: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Failed to fetch history"})
