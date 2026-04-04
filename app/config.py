import os
from dotenv import load_dotenv

load_dotenv()

# Groq configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.2-90b-vision-preview")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Database configuration (V2)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# File upload limits
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "5242880"))  # 5MB default
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}

# LLM request timeout (seconds)
LLM_TIMEOUT = 30

# System prompt for slide analysis
SYSTEM_PROMPT = (
    "You are a presentation expert. Analyze the provided slide image and return "
    "a JSON object with the following structure:\n"
    "{\n"
    '  "content": "detailed feedback about the slide content (text, data, messaging)",\n'
    '  "design": "detailed feedback about the visual design (layout, colors, typography, imagery)",\n'
    '  "tips": ["tip 1", "tip 2", "tip 3"]\n'
    "}\n"
    "Return ONLY valid JSON. No markdown, no explanations."
)
