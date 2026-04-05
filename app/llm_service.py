import base64
import hashlib
import io
import json
import logging
import re
from typing import Optional

import fitz  # PyMuPDF
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from PIL import Image

from app.config import (
    GIGACHAT_CREDENTIALS,
    GIGACHAT_MODEL,
    SYSTEM_PROMPT_ANALYSIS,
    IMPROVE_PROMPTS,
    SYSTEM_PROMPT_IMITATE,
    MAX_PDF_PAGES,
)

logger = logging.getLogger(__name__)


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute MD5 hash of file bytes."""
    return hashlib.md5(file_bytes).hexdigest()


def pdf_to_single_image(file_bytes: bytes, max_pages: int = MAX_PDF_PAGES) -> bytes:
    """
    Convert PDF to a single stitched image (all pages vertically).
    Returns JPEG bytes.
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page_count = min(len(doc), max_pages)

    if page_count == 0:
        raise ValueError("PDF has no pages")

    images = []
    for i in range(page_count):
        page = doc[i]
        pix = page.get_pixmap(dpi=150)
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
            max_tokens=1024,
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
            max_tokens=1024,
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


async def analyze_presentation(pdf_bytes: bytes) -> dict:
    """Analyze full presentation PDF."""
    image_bytes = pdf_to_single_image(pdf_bytes)
    image_b64 = image_to_base64(image_bytes)
    return _call_gigachat(SYSTEM_PROMPT_ANALYSIS, "Проанализируй эту презентацию.", image_b64)


async def improve_presentation(pdf_bytes: bytes, priority: str) -> dict:
    """Improve presentation by specific aspect."""
    if priority not in IMPROVE_PROMPTS:
        raise ValueError(f"Unknown priority: {priority}")

    image_bytes = pdf_to_single_image(pdf_bytes)
    image_b64 = image_to_base64(image_bytes)
    prompt = IMPROVE_PROMPTS[priority]
    return _call_gigachat(prompt, f"Улучши презентацию по аспекту: {priority}.", image_b64)


async def imitate_presentation(current_pdf_bytes: bytes, reference_pdf_bytes: bytes) -> dict:
    """Make current presentation similar to reference."""
    current_image = pdf_to_single_image(current_pdf_bytes)
    reference_image = pdf_to_single_image(reference_pdf_bytes)

    current_b64 = image_to_base64(current_image)
    reference_b64 = image_to_base64(reference_image)

    return _call_gigachat_two_images(
        SYSTEM_PROMPT_IMITATE,
        "Сделай текущую презентацию похожей на референсную.",
        current_b64,
        reference_b64,
    )
