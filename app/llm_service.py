import base64
import hashlib
import json
import logging
from typing import Optional

import httpx

from app.config import GROQ_API_KEY, GROQ_MODEL, GROQ_API_URL, SYSTEM_PROMPT, LLM_TIMEOUT

logger = logging.getLogger(__name__)


def image_to_base64(file_bytes: bytes) -> str:
    """Convert image bytes to base64 string."""
    return base64.b64encode(file_bytes).decode("utf-8")


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute MD5 hash of file bytes."""
    return hashlib.md5(file_bytes).hexdigest()


async def analyze_slide(file_bytes: bytes) -> dict:
    """
    Send image to Groq LLM and parse the JSON response.
    Returns dict with keys: content, design, tips.
    Raises exceptions on errors.
    """
    if not GROQ_API_KEY:
        logger.error("Groq API key is not configured")
        raise ValueError("LLM not configured: GROQ_API_KEY is not set")

    base64_image = image_to_base64(file_bytes)

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this slide and provide detailed feedback."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            response = await client.post(GROQ_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        logger.error("LLM request timed out")
        raise TimeoutError("Analysis taking too long")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from LLM: {e.response.status_code} - {e.response.text}")
        raise RuntimeError(f"LLM API error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Unexpected error calling LLM: {e}", exc_info=True)
        raise

    # Parse the response content as JSON
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        logger.error("Empty response from LLM")
        raise ValueError("Invalid response from AI")

    # Try to extract JSON from the response (LLM may wrap it in markdown)
    parsed = _extract_json(content)
    if parsed is None:
        logger.error(f"Failed to parse JSON from LLM response: {content}")
        raise ValueError("Invalid response from AI")

    return parsed


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON object from text that may contain markdown or extra text."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in markdown code fences
    if "```" in text:
        # Extract content between ```json and ``` or just ``` and ```
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

    # Try to find a JSON object by scanning for { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None
