import asyncio
import base64
import io
import json
import logging
import re
from typing import Optional, Callable

import fitz  # PyMuPDF
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from PIL import Image

from app.config import (
    GIGACHAT_CREDENTIALS,
    GIGACHAT_MODEL,
    SYSTEM_PROMPT_ANALYSIS,
    SYSTEM_PROMPT_ANALYSIS_OVERALL,
    IMPROVE_PROMPTS,
    SYSTEM_PROMPT_IMITATE,
    MAX_PDF_PAGES,
    SLIDE_BY_SLIDE,
    INSTRUCTION_PROMPTS,
    SYSTEM_PROMPT_EVALUATE_INSTRUCTIONS,
)

logger = logging.getLogger(__name__)

# Progress callback type: (current_slide, total_slides, status_message)
ProgressCallback = Callable[[int, int, str], None]


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute MD5 hash of file bytes."""
    import hashlib
    return hashlib.md5(file_bytes).hexdigest()


def pdf_to_per_slide_images(file_bytes: bytes, max_pages: int = MAX_PDF_PAGES) -> list[bytes]:
    """
    Convert PDF to a list of individual slide images.
    Returns list of JPEG bytes, one per slide.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page_count = min(len(doc), max_pages)

    if page_count == 0:
        raise ValueError("PDF has no pages")

    images = []
    for i in range(page_count):
        page = doc[i]
        pix = page.get_pixmap(dpi=100)  # Reduced from 150 for speed
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Convert to JPEG bytes
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85)
        images.append(output.getvalue())
    
    doc.close()
    return images


def pdf_to_single_image(file_bytes: bytes, max_pages: int = MAX_PDF_PAGES) -> bytes:
    """
    Convert PDF to a single stitched image (all pages vertically).
    Returns JPEG bytes. (Fallback for non-slide-by-slide mode)
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page_count = min(len(doc), max_pages)

    if page_count == 0:
        raise ValueError("PDF has no pages")

    images = []
    for i in range(page_count):
        page = doc[i]
        pix = page.get_pixmap(dpi=100)  # Reduced from 150 for speed
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    doc.close()

    # Stitch vertically
    total_height = sum(img.height for img in images)
    max_width = max(img.width for img in images)
    stitched = Image.new("RGB", (max_width, total_height), "white")

    y_offset = 0
    for img in images:
        stitched.paste(img, (0, y_offset))
        y_offset += img.height

    # Convert to JPEG bytes
    output = io.BytesIO()
    stitched.save(output, format="JPEG", quality=85)
    return output.getvalue()


def image_to_base64(file_bytes: bytes) -> str:
    """Convert image bytes to base64 string."""
    return base64.b64encode(file_bytes).decode("utf-8")


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON object from text that may contain markdown or extra text."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _generate_local_overall_assessment(slide_feedbacks: list) -> str:
    """Generate overall assessment locally from slide feedback (no API call)."""
    if not slide_feedbacks:
        return "No slides to analyze."
    
    total_slides = len(slide_feedbacks)
    all_strengths = []
    all_weaknesses = []
    
    for fb in slide_feedbacks:
        all_strengths.extend(fb.get("strengths", []))
        all_weaknesses.extend(fb.get("weaknesses", []))
    
    # Build summary
    parts = []
    parts.append(f"Analyzed {total_slides} slides.")
    
    if all_strengths:
        top_strengths = all_strengths[:3]
        parts.append(f"Key strengths: {'; '.join(top_strengths)}.")
    
    if all_weaknesses:
        top_weaknesses = all_weaknesses[:3]
        parts.append(f"Areas for improvement: {'; '.join(top_weaknesses)}.")
    
    if not parts:
        parts.append("Presentation analyzed successfully.")
    
    return " ".join(parts)


def _extract_local_action_plan(slide_feedbacks: list) -> list:
    """Extract action plan locally from slide suggestions."""
    all_suggestions = []
    for fb in slide_feedbacks:
        all_suggestions.extend(fb.get("suggestions", []))
    
    # Return top 5 unique suggestions
    seen = set()
    unique = []
    for s in all_suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)
            if len(unique) >= 5:
                break
    
    return unique if unique else ["Review each slide for specific improvements"]


def _extract_local_final_recommendation(slide_feedbacks: list) -> str:
    """Extract final recommendation locally."""
    if not slide_feedbacks:
        return "Review presentation for improvements."
    
    # Count common themes
    all_weaknesses = []
    for fb in slide_feedbacks:
        all_weaknesses.extend(fb.get("weaknesses", []))
    
    if all_weaknesses:
        return f"Focus on addressing: {all_weaknesses[0]}"
    
    return "Presentation looks good. Consider minor refinements."


async def _process_slide_two_images_async(
    slide_idx: int,
    current_img: bytes,
    reference_img: bytes,
    system_prompt: str,
    user_prompt: str,
    progress_callback: ProgressCallback = None,
    total_slides: int = 0
) -> dict:
    """Process a single slide with two images (current + reference) sequentially."""
    correct_slide_number = slide_idx + 1
    current_b64 = image_to_base64(current_img)
    reference_b64 = image_to_base64(reference_img)

    if progress_callback:
        progress_callback(correct_slide_number, total_slides, f"Comparing slide {correct_slide_number}...")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _call_gigachat_two_images(system_prompt, user_prompt.format(idx=correct_slide_number), current_b64, reference_b64)
        )
        # Enforce correct slide number regardless of what LLM returns
        result["slide_number"] = correct_slide_number
        return result
    except Exception as e:
        logger.error(f"Failed to compare slide {correct_slide_number}: {e}")
        return {
            "slide_number": correct_slide_number,
            "feedback": f"Failed to compare slide {correct_slide_number}: {str(e)}",
            "suggestions": []
        }


async def _process_slide_async(
    slide_idx: int,
    slide_img: bytes,
    system_prompt: str,
    user_prompt: str,
    progress_callback: ProgressCallback = None,
    total_slides: int = 0,
    context_text: str = ""
) -> dict:
    """Process a single slide sequentially."""
    slide_b64 = image_to_base64(slide_img)
    correct_slide_number = slide_idx + 1

    if progress_callback:
        progress_callback(correct_slide_number, total_slides, f"Analyzing slide {correct_slide_number}...")

    try:
        # Build context from previous slides to avoid repetition
        full_prompt = system_prompt
        if context_text:
            full_prompt += context_text

        # Run blocking GigaChat call in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _call_gigachat(full_prompt, user_prompt.format(idx=correct_slide_number), slide_b64)
        )
        # Enforce correct slide number regardless of what LLM returns
        result["slide_number"] = correct_slide_number
        return result
    except Exception as e:
        logger.error(f"Failed to analyze slide {correct_slide_number}: {e}")
        return {
            "slide_number": correct_slide_number,
            "feedback": f"Failed to analyze slide {correct_slide_number}: {str(e)}",
            "strengths": [],
            "weaknesses": [],
            "suggestions": []
        }


def _call_gigachat(system_prompt: str, user_text: str, image_base64: str) -> dict:
    """Send image + prompt to GigaChat and parse JSON response."""
    if not GIGACHAT_CREDENTIALS:
        raise ValueError("LLM not configured: GIGACHAT_CREDENTIALS is not set")

    with GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        verify_ssl_certs=False,
        model=GIGACHAT_MODEL,
    ) as client:
        file_obj = io.BytesIO(base64.b64decode(image_base64))
        uploaded = client.upload_file(("slide.jpg", file_obj), purpose="general")
        file_id = uploaded.id_
        logger.info(f"Uploaded file: {file_id}")

        chat_payload = Chat(
            model=GIGACHAT_MODEL,
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                Messages(role=MessagesRole.USER, content=user_text, attachments=[file_id]),
            ],
            temperature=0.3,
            max_tokens=512,  # Reduced from 1024 for speed
        )

        response = client.chat(chat_payload)
        content = response.choices[0].message.content

    if not content:
        raise ValueError("Empty response from GigaChat")

    parsed = _extract_json(content)
    if parsed is None:
        logger.error(f"Failed to parse JSON: {content}")
        raise ValueError("Invalid response from AI")

    return parsed


def _call_gigachat_two_images(
    system_prompt: str, user_text: str, image1_base64: str, image2_base64: str
) -> dict:
    """Send two images (current + reference) to GigaChat for comparison."""
    if not GIGACHAT_CREDENTIALS:
        raise ValueError("LLM not configured: GIGACHAT_CREDENTIALS is not set")

    with GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        verify_ssl_certs=False,
        model=GIGACHAT_MODEL,
    ) as client:
        # Upload current presentation
        file_obj1 = io.BytesIO(base64.b64decode(image1_base64))
        uploaded1 = client.upload_file(("current.jpg", file_obj1), purpose="general")
        file_id1 = uploaded1.id_

        # Upload reference presentation
        file_obj2 = io.BytesIO(base64.b64decode(image2_base64))
        uploaded2 = client.upload_file(("reference.jpg", file_obj2), purpose="general")
        file_id2 = uploaded2.id_

        logger.info(f"Uploaded files: {file_id1}, {file_id2}")

        chat_payload = Chat(
            model=GIGACHAT_MODEL,
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                Messages(
                    role=MessagesRole.USER,
                    content=user_text,
                    attachments=[file_id1, file_id2],
                ),
            ],
            temperature=0.3,
            max_tokens=512,  # Reduced from 1024 for speed
        )

        response = client.chat(chat_payload)
        content = response.choices[0].message.content

    if not content:
        raise ValueError("Empty response from GigaChat")

    parsed = _extract_json(content)
    if parsed is None:
        logger.error(f"Failed to parse JSON: {content}")
        raise ValueError("Invalid response from AI")

    return parsed


async def analyze_presentation(pdf_bytes: bytes, progress_callback: ProgressCallback = None) -> dict:
    """
    Analyze full presentation PDF.
    If SLIDE_BY_SLIDE is True, processes each slide individually and aggregates results.
    Uses parallel processing for speed.
    """
    if SLIDE_BY_SLIDE:
        logger.info("Using slide-by-slide analysis mode (sequential)")
        slide_images = pdf_to_per_slide_images(pdf_bytes)
        total_slides = len(slide_images)
        
        # Process slides sequentially
        slide_feedbacks = []
        for idx, slide_img in enumerate(slide_images):
            result = await _process_slide_async(
                idx, slide_img,
                SYSTEM_PROMPT_ANALYSIS,
                "Analyze slide {idx}.",
                progress_callback,
                total_slides,
                ""
            )
            slide_feedbacks.append(result)
        
        # Generate overall assessment LOCALLY (no API call)
        if progress_callback:
            progress_callback(total_slides, total_slides, "Generating overall assessment...")
        
        summary_text = "Slide analysis results:\n"
        for fb in slide_feedbacks:
            summary_text += f"Slide {fb.get('slide_number', '?')}: {fb.get('feedback', '')}\n"
            if fb.get('strengths'):
                summary_text += f"  Strengths: {', '.join(fb['strengths'])}\n"
            if fb.get('weaknesses'):
                summary_text += f"  Weaknesses: {', '.join(fb['weaknesses'])}\n"
        
        # Generate overall assessment locally from slide feedback
        overall_assessment = _generate_local_overall_assessment(slide_feedbacks)
        
        # Build slide_by_slide array from individual feedbacks
        slide_by_slide = []
        for fb in slide_feedbacks:
            slide_by_slide.append({
                "slide_number": fb.get("slide_number", 0),
                "feedback": fb.get("feedback", ""),
                "strengths": fb.get("strengths", []),
                "weaknesses": fb.get("weaknesses", []),
                "suggestions": fb.get("suggestions", [])
            })
        
        return {
            "overall_assessment": overall_assessment,
            "slide_by_slide": slide_by_slide,
            "action_plan": _extract_local_action_plan(slide_feedbacks),
            "final_recommendation": _extract_local_final_recommendation(slide_feedbacks),
        }
    else:
        # Legacy mode: process as single stitched image
        logger.info("Using legacy single-image analysis mode")
        image_bytes = pdf_to_single_image(pdf_bytes)
        image_b64 = image_to_base64(image_bytes)
        return _call_gigachat(SYSTEM_PROMPT_ANALYSIS, "Analyze this presentation.", image_b64)


async def improve_presentation(pdf_bytes: bytes, priority: str, progress_callback: ProgressCallback = None) -> dict:
    """
    Improve presentation by specific aspect.
    If SLIDE_BY_SLIDE is True, processes each slide individually (parallel).
    """
    if priority not in IMPROVE_PROMPTS:
        raise ValueError(f"Unknown priority: {priority}")

    if SLIDE_BY_SLIDE:
        logger.info(f"Using slide-by-slide improvement mode for priority: {priority} (sequential)")
        slide_images = pdf_to_per_slide_images(pdf_bytes)
        total_slides = len(slide_images)

        # Process slides sequentially
        slide_feedbacks = []
        for idx, slide_img in enumerate(slide_images):
            result = await _process_slide_async(
                idx, slide_img,
                IMPROVE_PROMPTS[priority],
                f"Improve slide {{idx}} by aspect: {priority}.",
                progress_callback,
                total_slides,
                ""
            )
            slide_feedbacks.append(result)

        # Aggregate results
        slide_by_slide = []
        all_suggestions = []
        for fb in slide_feedbacks:
            slide_by_slide.append({
                "slide_number": fb.get("slide_number", 0),
                "feedback": fb.get("feedback", ""),
                "suggestions": fb.get("suggestions", [])
            })
            all_suggestions.extend(fb.get("suggestions", []))

        return {
            "overall_assessment": f"Improved {len(slide_feedbacks)} slides for aspect: {priority}",
            "slide_by_slide": slide_by_slide,
            "action_plan": all_suggestions[:5],
            "final_recommendation": f"Main advice: apply improvements for '{priority}' aspect to all slides",
        }
    else:
        # Legacy mode
        logger.info(f"Using legacy single-image improvement mode for priority: {priority}")
        image_bytes = pdf_to_single_image(pdf_bytes)
        image_b64 = image_to_base64(image_bytes)
        prompt = IMPROVE_PROMPTS[priority]
        return _call_gigachat(prompt, f"Improve presentation by aspect: {priority}.", image_b64)


async def imitate_presentation(current_pdf_bytes: bytes, reference_pdf_bytes: bytes, progress_callback: ProgressCallback = None) -> dict:
    """
    Make current presentation similar to reference.
    If SLIDE_BY_SLIDE is True, processes each slide pair individually (parallel).
    """
    if SLIDE_BY_SLIDE:
        logger.info("Using slide-by-slide imitation mode (sequential)")
        current_images = pdf_to_per_slide_images(current_pdf_bytes)
        reference_images = pdf_to_per_slide_images(reference_pdf_bytes)

        # Use minimum of both slide counts
        min_slides = min(len(current_images), len(reference_images))
        total_slides = len(current_images)

        # Process slides sequentially
        slide_feedbacks = []
        for idx in range(min_slides):
            result = await _process_slide_two_images_async(
                idx,
                current_images[idx],
                reference_images[idx],
                SYSTEM_PROMPT_IMITATE,
                "Make current slide {idx} similar to reference slide {idx}.",
                progress_callback,
                total_slides
            )
            slide_feedbacks.append(result)

        # Handle extra slides in either presentation
        for idx in range(min_slides, len(current_images)):
            slide_feedbacks.append({
                "slide_number": idx + 1,
                "feedback": "No corresponding slide in reference presentation",
                "suggestions": []
            })

        slide_by_slide = []
        all_suggestions = []
        for fb in slide_feedbacks:
            slide_by_slide.append({
                "slide_number": fb.get("slide_number", 0),
                "feedback": fb.get("feedback", ""),
                "suggestions": fb.get("suggestions", [])
            })
            all_suggestions.extend(fb.get("suggestions", []))
        
        return {
            "overall_assessment": f"Compared {min_slides} slides with reference",
            "slide_by_slide": slide_by_slide,
            "action_plan": all_suggestions[:5],
            "final_recommendation": "Main advice: apply stylistic changes from the reference",
        }
    else:
        # Legacy mode
        logger.info("Using legacy single-image imitation mode")
        current_image = pdf_to_single_image(current_pdf_bytes)
        reference_image = pdf_to_single_image(reference_pdf_bytes)

        current_b64 = image_to_base64(current_image)
        reference_b64 = image_to_base64(reference_image)

        return _call_gigachat_two_images(
            SYSTEM_PROMPT_IMITATE,
            "Make the current presentation similar to the reference.",
            current_b64,
            reference_b64,
        )


async def generate_instructions(pdf_bytes: bytes, aspect: str, progress_callback: ProgressCallback = None) -> dict:
    """
    Generate actionable instructions for improving a specific aspect of the presentation.
    Returns JSON with per-slide instructions that can be stored in DB.
    """
    if aspect not in INSTRUCTION_PROMPTS:
        raise ValueError(f"Unknown aspect: {aspect}")

    logger.info(f"Generating instructions for aspect: {aspect}")
    slide_images = pdf_to_per_slide_images(pdf_bytes)
    total_slides = len(slide_images)
    
    instructions = []
    for idx, slide_img in enumerate(slide_images):
        slide_b64 = image_to_base64(slide_img)
        correct_slide_number = idx + 1

        if progress_callback:
            progress_callback(correct_slide_number, total_slides, f"Generating instructions for slide {correct_slide_number}...")

        try:
            result = _call_gigachat(
                INSTRUCTION_PROMPTS[aspect],
                f"Create instructions to improve slide {correct_slide_number} for aspect: {aspect}.",
                slide_b64
            )

            # Extract instruction for this slide — enforce correct slide number
            if "instructions" in result:
                for inst in result["instructions"]:
                    inst["slide_number"] = correct_slide_number
                    instructions.append(inst)
            else:
                # Fallback: treat entire response as instruction for this slide
                instructions.append({
                    "slide_number": correct_slide_number,
                    "instruction": result.get("feedback", result.get("instruction", "No specific instruction generated")),
                    "priority": result.get("priority", "medium")
                })

            logger.info(f"Generated instructions for slide {correct_slide_number}")
        except Exception as e:
            logger.error(f"Failed to generate instructions for slide {correct_slide_number}: {e}")
            instructions.append({
                "slide_number": correct_slide_number,
                "instruction": f"Failed to generate instruction: {str(e)}",
                "priority": "high"
            })
    
    return {
        "aspect": aspect,
        "instructions": instructions,
        "summary": f"Instructions generated for {total_slides} slides to improve {aspect} aspect",
    }


async def evaluate_against_instructions(
    pdf_bytes: bytes,
    stored_instructions: dict,
    progress_callback: ProgressCallback = None
) -> dict:
    """
    Evaluate whether the updated presentation has followed the stored instructions.
    Returns evaluation result with resolved status and updated instructions if needed.
    """
    logger.info("Evaluating presentation against stored instructions")
    slide_images = pdf_to_per_slide_images(pdf_bytes)
    total_slides = len(slide_images)
    
    evaluations = []
    unresolved_instructions = []
    
    for idx, slide_img in enumerate(slide_images):
        slide_b64 = image_to_base64(slide_img)
        correct_slide_number = idx + 1

        if progress_callback:
            progress_callback(correct_slide_number, total_slides, f"Evaluating slide {correct_slide_number}...")

        # Find instructions for this slide
        slide_instructions = [
            inst for inst in stored_instructions.get("instructions", [])
            if inst.get("slide_number") == correct_slide_number
        ]

        if not slide_instructions:
            # No instruction for this slide, skip evaluation
            evaluations.append({
                "slide_number": correct_slide_number,
                "instruction": "No instruction provided",
                "status": "resolved",
                "comment": "No specific instruction was given for this slide"
            })
            continue

        try:
            # Build evaluation prompt with original instruction
            instruction_text = "; ".join([inst.get("instruction", "") for inst in slide_instructions])

            eval_prompt = (
                f"Evaluate whether slide {correct_slide_number} has followed this instruction: {instruction_text}\n"
                f"Return JSON with status (resolved/partial/unresolved) and comment explaining why."
            )

            result = _call_gigachat(
                SYSTEM_PROMPT_EVALUATE_INSTRUCTIONS,
                eval_prompt,
                slide_b64
            )

            # Extract evaluation for this slide — enforce correct slide number
            if "evaluation" in result and len(result["evaluation"]) > 0:
                eval_item = result["evaluation"][0]
                eval_item["slide_number"] = correct_slide_number
                evaluations.append(eval_item)

                # Check if resolved
                if eval_item.get("status") in ["partial", "unresolved"]:
                    if "new_instructions" in result:
                        for new_inst in result["new_instructions"]:
                            new_inst["slide_number"] = correct_slide_number
                            unresolved_instructions.append(new_inst)
            else:
                # Fallback
                evaluations.append({
                    "slide_number": correct_slide_number,
                    "instruction": instruction_text,
                    "status": "unresolved",
                    "comment": "Could not evaluate instruction"
                })
                unresolved_instructions.append({
                    "slide_number": correct_slide_number,
                    "instruction": instruction_text,
                    "priority": "high"
                })

            logger.info(f"Evaluated slide {correct_slide_number}")
        except Exception as e:
            logger.error(f"Failed to evaluate slide {correct_slide_number}: {e}")
            evaluations.append({
                "slide_number": correct_slide_number,
                "instruction": "Evaluation failed",
                "status": "unresolved",
                "comment": str(e)
            })
            unresolved_instructions.append({
                "slide_number": correct_slide_number,
                "instruction": "Re-evaluate this slide",
                "priority": "high"
            })
    
    # Determine overall resolution
    all_resolved = all(ev.get("status") == "resolved" for ev in evaluations)
    
    return {
        "resolved": all_resolved,
        "evaluation": evaluations,
        "summary": "All instructions followed" if all_resolved else "Some instructions still need work",
        "new_instructions": {
            "aspect": stored_instructions.get("aspect", "unknown"),
            "instructions": unresolved_instructions,
            "summary": "Updated instructions for remaining issues"
        } if not all_resolved else None
    }
