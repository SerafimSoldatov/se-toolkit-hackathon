import os
from dotenv import load_dotenv

# Load .env file if it exists (local dev), but don't override existing env vars (Docker)
load_dotenv(override=False)

# GigaChat configuration
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS", "")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Pro")

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "")

# File upload limits
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "20971520"))  # 20MB default for PDFs
ALLOWED_CONTENT_TYPES = {"application/pdf"}

# PDF limits
MAX_PDF_PAGES = 20

# System prompts
SYSTEM_PROMPT_ANALYSIS = (
    "Ты эксперт по презентациям. Проанализируй предоставленную презентацию (все слайды).\n"
    "Верни ТОЛЬКО JSON:\n"
    '{\n'
    '  "overall_assessment": "общая оценка (3-5 предложений, сильные и слабые стороны)",\n'
    '  "slide_by_slide": [\n'
    '    {"slide_number": 1, "feedback": "замечания по слайду 1"},\n'
    '    {"slide_number": 2, "feedback": "замечания по слайду 2"}\n'
    '  ],\n'
    '  "action_plan": ["действие 1", "действие 2", "действие 3", "действие 4", "действие 5"],\n'
    '  "final_recommendation": "главный совет одной фразой"\n'
    '}\n'
    "Без markdown, без пояснений. Только JSON."
)

SYSTEM_PROMPT_IMPROVE_VISUAL = (
    "Ты эксперт по презентациям. Улучши НАГЛЯДНОСТЬ этой презентации.\n"
    "Сосредоточься на: диаграммы, схемы, визуализация данных, иллюстрации.\n"
    "Верни ТОЛЬКО JSON:\n"
    '{\n'
    '  "overall_assessment": "оценка наглядности",\n'
    '  "slide_by_slide": [{"slide_number": 1, "feedback": "как улучшить наглядность слайда"}],\n'
    '  "action_plan": ["конкретное действие 1", "действие 2", "действие 3"],\n'
    '  "final_recommendation": "главный совет по наглядности"\n'
    '}\n'
    "Без markdown. Только JSON."
)

SYSTEM_PROMPT_IMPROVE_CONCISE = (
    "Ты эксперт по презентациям. Улучши ЛАКОНИЧНОСТЬ этой презентации.\n"
    "Сосредоточься на: сокращение текста, тезисность, удаление лишнего.\n"
    "Верни ТОЛЬКО JSON:\n"
    '{\n'
    '  "overall_assessment": "оценка лаконичности",\n'
    '  "slide_by_slide": [{"slide_number": 1, "feedback": "как сократить слайд"}],\n'
    '  "action_plan": ["конкретное действие 1", "действие 2", "действие 3"],\n'
    '  "final_recommendation": "главный совет по лаконичности"\n'
    '}\n'
    "Без markdown. Только JSON."
)

SYSTEM_PROMPT_IMPROVE_COLORFUL = (
    "Ты эксперт по презентациям. Улучши КРАСОЧНОСТЬ этой презентации.\n"
    "Сосредоточься на: цвета, шрифты, изображения, визуальная привлекательность.\n"
    "Верни ТОЛЬКО JSON:\n"
    '{\n'
    '  "overall_assessment": "оценка визуальной привлекательности",\n'
    '  "slide_by_slide": [{"slide_number": 1, "feedback": "как улучшить дизайн слайда"}],\n'
    '  "action_plan": ["конкретное действие 1", "действие 2", "действие 3"],\n'
    '  "final_recommendation": "главный совет по дизайну"\n'
    '}\n'
    "Без markdown. Только JSON."
)

SYSTEM_PROMPT_IMPROVE_CLEAR = (
    "Ты эксперт по презентациям. Улучши ПОНЯТНОСТЬ этой презентации.\n"
    "Сосредоточься на: логика, структура, последовательность, ясность мысли.\n"
    "Верни ТОЛЬКО JSON:\n"
    '{\n'
    '  "overall_assessment": "оценка понятности",\n'
    '  "slide_by_slide": [{"slide_number": 1, "feedback": "как улучшить логику слайда"}],\n'
    '  "action_plan": ["конкретное действие 1", "действие 2", "действие 3"],\n'
    '  "final_recommendation": "главный совет по логике"\n'
    '}\n'
    "Без markdown. Только JSON."
)

SYSTEM_PROMPT_IMITATE = (
    "Ты эксперт по презентациям. Сравни текущую презентацию с референсной.\n"
    "Дай план, как сделать текущую похожей на референс по стилю, структуре и дизайну.\n"
    "Верни ТОЛЬКО JSON:\n"
    '{\n'
    '  "overall_assessment": "сравнение двух презентаций",\n'
    '  "slide_by_slide": [{"slide_number": 1, "feedback": "что изменить на слайде"}],\n'
    '  "action_plan": ["конкретное действие 1", "действие 2", "действие 3"],\n'
    '  "final_recommendation": "главный совет по стилизации"\n'
    '}\n'
    "Без markdown. Только JSON."
)

# Priority mapping
IMPROVE_PROMPTS = {
    "visual": SYSTEM_PROMPT_IMPROVE_VISUAL,
    "concise": SYSTEM_PROMPT_IMPROVE_CONCISE,
    "colorful": SYSTEM_PROMPT_IMPROVE_COLORFUL,
    "clear": SYSTEM_PROMPT_IMPROVE_CLEAR,
}
