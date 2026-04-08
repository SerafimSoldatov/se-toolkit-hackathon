import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import MAX_FILE_SIZE, ALLOWED_CONTENT_TYPES, DATABASE_URL, SLIDE_BY_SLIDE
from app.database import init_db, Base
import app.database as db_module
from app.llm_service import (
    analyze_presentation,
    improve_presentation,
    imitate_presentation,
    compute_file_hash,
    generate_instructions,
    evaluate_against_instructions,
)
from app.models import Analysis

import fitz  # For slide count validation

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


app = FastAPI(title="SlideWise (Slide-by-Slide)", lifespan=lifespan)

# Store for progress updates
progress_store: dict[str, dict] = {}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"{request.method} {request.url.path} - {response.status_code} ({duration:.2f}s)")
    return response


@app.get("/progress/{task_id}")
async def progress_stream(task_id: str):
    """Server-Sent Events endpoint for real-time progress."""
    async def event_stream() -> AsyncGenerator[str, None]:
        import asyncio
        while True:
            if task_id in progress_store:
                progress = progress_store[task_id]
                yield f"data: {json.dumps(progress)}\n\n"

                # Stop streaming when complete
                if progress.get("status") == "complete" or progress.get("status") == "error":
                    break
            else:
                yield f"data: {json.dumps({'status': 'waiting'})}\n\n"

            await asyncio.sleep(0.3)
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


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
async def analyze(request: Request, file: UploadFile = File(...), task_id: str = Form(None)):
    """Primary analysis: upload PDF, get full presentation feedback."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Use client-provided task_id or generate one
    if not task_id:
        task_id = str(uuid.uuid4())
    
    # Initialize progress
    progress_store[task_id] = {
        "status": "starting",
        "current_slide": 0,
        "total_slides": 0,
        "message": "Preparing to analyze presentation...",
    }

    def update_progress(current: int, total: int, message: str):
        progress_store[task_id] = {
            "status": "processing",
            "current_slide": current,
            "total_slides": total,
            "message": message,
        }

    try:
        result = await analyze_presentation(file_bytes, progress_callback=update_progress)

        # Mark as complete
        progress_store[task_id] = {
            "status": "complete",
            "current_slide": progress_store[task_id].get("total_slides", 0),
            "total_slides": progress_store[task_id].get("total_slides", 0),
            "message": "Analysis complete!",
        }

        session_id = get_session_id(request)
        
        # Save to DB if available
        analysis_id = None
        if DATABASE_URL:
            try:
                async with db_module.async_session() as db:
                    slide_count = len(result.get("slide_by_slide", []))
                    record = Analysis(
                        session_id=session_id,
                        presentation_hash=compute_file_hash(file_bytes),
                        original_feedback=json.dumps(result),
                        slide_count=slide_count,
                    )
                    db.add(record)
                    await db.commit()
                    await db.refresh(record)
                    analysis_id = record.id
            except Exception as db_err:
                logger.warning(f"Failed to save analysis to DB: {db_err}")

        response = JSONResponse(content={"result": result, "task_id": task_id, "analysis_id": analysis_id})
        return set_session_cookie(response, session_id)
    except ValueError as e:
        if "not configured" in str(e):
            progress_store[task_id] = {"status": "error", "message": "LLM not configured"}
            return JSONResponse(status_code=500, content={"error": "LLM not configured", "task_id": task_id})
        progress_store[task_id] = {"status": "error", "message": str(e)}
        return JSONResponse(status_code=502, content={"error": str(e), "task_id": task_id})
    except RuntimeError as e:
        progress_store[task_id] = {"status": "error", "message": str(e)}
        return JSONResponse(status_code=502, content={"error": str(e), "task_id": task_id})
    except Exception as e:
        logger.error(f"Unexpected error in analyze: {e}", exc_info=True)
        progress_store[task_id] = {"status": "error", "message": "Internal server error"}
        return JSONResponse(status_code=500, content={"error": "Internal server error", "task_id": task_id})


@app.post("/improve")
async def improve(
    request: Request,
    file: UploadFile = File(...),
    priority: str = Form(None),
    reference_file: UploadFile = File(None),
    task_id: str = Form(None),
):
    """Improve presentation: by aspect or by reference."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    if not task_id:
        task_id = str(uuid.uuid4())
    
    # Initialize progress
    progress_store[task_id] = {
        "status": "starting",
        "current_slide": 0,
        "total_slides": 0,
        "message": "Preparing to improve presentation...",
    }

    def update_progress(current: int, total: int, message: str):
        progress_store[task_id] = {
            "status": "processing",
            "current_slide": current,
            "total_slides": total,
            "message": message,
        }

    try:
        if reference_file:
            # Imitate mode: two PDFs
            ref_bytes = await reference_file.read()
            result = await imitate_presentation(file_bytes, ref_bytes, progress_callback=update_progress)
        elif priority:
            result = await improve_presentation(file_bytes, priority, progress_callback=update_progress)
        else:
            progress_store[task_id] = {"status": "error", "message": "Missing parameters"}
            raise HTTPException(status_code=400, detail="Either priority or reference_file required")
        
        # Mark as complete
        progress_store[task_id] = {
            "status": "complete",
            "current_slide": progress_store[task_id].get("total_slides", 0),
            "total_slides": progress_store[task_id].get("total_slides", 0),
            "message": "Improvement complete!",
        }
        
        session_id = get_session_id(request)
        response = JSONResponse(content={"result": result, "task_id": task_id})
        return set_session_cookie(response, session_id)
    except ValueError as e:
        progress_store[task_id] = {"status": "error", "message": str(e)}
        return JSONResponse(status_code=502, content={"error": str(e), "task_id": task_id})
    except RuntimeError as e:
        progress_store[task_id] = {"status": "error", "message": str(e)}
        return JSONResponse(status_code=502, content={"error": str(e), "task_id": task_id})
    except Exception as e:
        logger.error(f"Unexpected error in improve: {e}", exc_info=True)
        progress_store[task_id] = {"status": "error", "message": "Internal server error"}
        return JSONResponse(status_code=500, content={"error": "Internal server error", "task_id": task_id})


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


@app.post("/start-improvement")
async def start_improvement(
    request: Request,
    analysis_id: int = Form(...),
    aspect: str = Form(...),
    task_id: str = Form(None),
):
    """Start iterative improvement cycle: generate instructions for chosen aspect."""
    if not DATABASE_URL:
        return JSONResponse(status_code=501, content={"error": "Database not available"})

    if aspect not in ["visual", "concise", "colorful", "clear"]:
        raise HTTPException(status_code=400, detail="Invalid aspect. Choose: visual, concise, colorful, or clear")

    session_id = get_session_id(request)

    try:
        async with db_module.async_session() as db:
            # Find the analysis record
            stmt = select(Analysis).where(Analysis.id == analysis_id, Analysis.session_id == session_id)
            result = await db.execute(stmt)
            record = result.scalar_one_or_none()

            if not record:
                raise HTTPException(status_code=404, detail="Analysis not found")

            if not record.original_feedback:
                raise HTTPException(status_code=400, detail="No analysis data to improve from")

            # Get slide count from original feedback
            original_data = json.loads(record.original_feedback)
            slide_count = len(original_data.get("slide_by_slide", []))

            # Use client-provided task_id or generate one
            if not task_id:
                task_id = str(uuid.uuid4())
            progress_store[task_id] = {
                "status": "starting",
                "current_slide": 0,
                "total_slides": 0,
                "message": "Generating improvement instructions...",
            }

            def update_progress(current: int, total: int, message: str):
                progress_store[task_id] = {
                    "status": "processing",
                    "current_slide": current,
                    "total_slides": total,
                    "message": message,
                }

            # We need the original PDF to generate instructions, but we don't have it stored
            # For now, we'll use the feedback data to create instructions
            # This is a limitation - we need to store the PDF or regenerate from feedback
            instructions = {
                "aspect": aspect,
                "instructions": [],
                "summary": f"Improve {aspect} aspect based on previous analysis",
            }

            # Extract instructions from original feedback
            for slide in original_data.get("slide_by_slide", []):
                if slide.get("suggestions"):
                    for suggestion in slide["suggestions"]:
                        instructions["instructions"].append({
                            "slide_number": slide["slide_number"],
                            "instruction": suggestion,
                            "priority": "medium",
                        })

            # Update database
            record.aspect = aspect
            record.instructions = json.dumps(instructions)
            record.iteration_count = 0
            record.resolved = False
            record.slide_count = slide_count
            await db.commit()

            progress_store[task_id] = {
                "status": "complete",
                "current_slide": slide_count,
                "total_slides": slide_count,
                "message": "Instructions generated!",
            }

            response = JSONResponse(content={"instructions": instructions, "task_id": task_id, "slide_count": slide_count})
            return set_session_cookie(response, session_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting improvement: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Failed to start improvement"})


@app.post("/check-improvement")
async def check_improvement(
    request: Request,
    analysis_id: int = Form(...),
    file: UploadFile = File(...),
    task_id: str = Form(None),
):
    """Upload modified presentation and check against stored instructions."""
    if not DATABASE_URL:
        return JSONResponse(status_code=501, content={"error": "Database not available"})

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    if not task_id:
        task_id = str(uuid.uuid4())

    session_id = get_session_id(request)

    try:
        async with db_module.async_session() as db:
            # Find the analysis record
            stmt = select(Analysis).where(Analysis.id == analysis_id, Analysis.session_id == session_id)
            result = await db.execute(stmt)
            record = result.scalar_one_or_none()

            if not record:
                raise HTTPException(status_code=404, detail="Analysis not found")

            if not record.instructions:
                raise HTTPException(status_code=400, detail="No instructions to check against")

            # Validate slide count
            new_slide_count = len(fitz.open(stream=file_bytes, filetype="pdf"))
            if new_slide_count != record.slide_count:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"Slide count mismatch. Expected {record.slide_count} slides, got {new_slide_count}. Presentation must have the same number of slides.",
                        "expected_slides": record.slide_count,
                        "actual_slides": new_slide_count,
                    }
                )

            stored_instructions = json.loads(record.instructions)

            # Setup progress tracking
            task_id = str(uuid.uuid4())
            progress_store[task_id] = {
                "status": "starting",
                "current_slide": 0,
                "total_slides": 0,
                "message": "Evaluating presentation against instructions...",
            }

            def update_progress(current: int, total: int, message: str):
                progress_store[task_id] = {
                    "status": "processing",
                    "current_slide": current,
                    "total_slides": total,
                    "message": message,
                }

            # Evaluate
            evaluation = await evaluate_against_instructions(
                file_bytes,
                stored_instructions,
                progress_callback=update_progress
            )

            # Update database
            record.iteration_count += 1
            record.presentation_hash = compute_file_hash(file_bytes)

            if evaluation["resolved"]:
                record.resolved = True
                record.instructions = None  # Clear instructions when resolved
                progress_store[task_id] = {
                    "status": "complete",
                    "current_slide": record.slide_count,
                    "total_slides": record.slide_count,
                    "message": "All instructions followed! 🎉",
                }
            else:
                # Store updated instructions
                if evaluation.get("new_instructions"):
                    record.instructions = json.dumps(evaluation["new_instructions"])
                progress_store[task_id] = {
                    "status": "complete",
                    "current_slide": record.slide_count,
                    "total_slides": record.slide_count,
                    "message": "Issues remain. Updated instructions provided.",
                }

            await db.commit()

            response = JSONResponse(content={
                "evaluation": evaluation,
                "task_id": task_id,
                "resolved": evaluation["resolved"],
                "iteration_count": record.iteration_count,
            })
            return set_session_cookie(response, session_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking improvement: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Failed to check improvement"})


@app.get("/current-instructions/{analysis_id}")
async def get_current_instructions(request: Request, analysis_id: int):
    """Get current active instructions for an analysis."""
    if not DATABASE_URL:
        return JSONResponse(status_code=501, content={"error": "Database not available"})

    session_id = get_session_id(request)

    try:
        async with db_module.async_session() as db:
            stmt = select(Analysis).where(Analysis.id == analysis_id, Analysis.session_id == session_id)
            result = await db.execute(stmt)
            record = result.scalar_one_or_none()

            if not record:
                raise HTTPException(status_code=404, detail="Analysis not found")

            if not record.instructions:
                return JSONResponse(content={"instructions": None, "resolved": record.resolved})

            instructions = json.loads(record.instructions)
            return JSONResponse(content={
                "instructions": instructions,
                "aspect": record.aspect,
                "iteration_count": record.iteration_count,
                "resolved": record.resolved,
                "slide_count": record.slide_count,
            })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching instructions: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Failed to fetch instructions"})
