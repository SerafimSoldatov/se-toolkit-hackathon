# SlideWise — Version 1 (Basic)

AI-powered slide analysis — basic version without database.

## Quick Start

### Local Development

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000`

### Docker

```bash
docker build -t slidewise-v1 .
docker run -p 8000:8000 --env-file .env slidewise-v1
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve the HTML page |
| POST | `/analyze` | Upload an image, get JSON feedback |

## Features

- Drag & drop slide upload (JPG, PNG, PDF)
- AI-powered content and design analysis
- 3 actionable tips per slide
- No database — stateless, simple deployment
