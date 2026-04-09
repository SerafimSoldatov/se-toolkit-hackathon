# SlideWise (Slide-by-Slide Iteration) — AI Presentation Analysis and Improvement

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)
![GigaChat](https://img.shields.io/badge/AI-GigaChat--2--Pro-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**Slide-by-Slide Processing** — Each slide is analyzed individually for specific, targeted feedback instead of generic repeated messages.

## Key Improvements Over Original

- ✅ **Per-Slide Analysis:** Each slide is sent to GigaChat individually for specific feedback
- ✅ **Rich Feedback Structure:** Strengths, weaknesses, and suggestions per slide
- ✅ **Better Improvement Modes:** All 4 aspects (visual, concise, colorful, clear) work per-slide
- ✅ **Slide-by-Slide Imitation:** Compare corresponding slides with reference presentation
- ✅ **Configurable:** Toggle between slide-by-slide and legacy mode via `SLIDE_BY_SLIDE` env var

## Features

- **Full Presentation Analysis:** Upload a complete PDF (up to 20 pages), not just one slide
- **4 Improvement Modes:** Visual clarity, conciseness, colorful design, logical clarity
- **Reference Imitation:** Make your presentation similar to a reference example
- **PostgreSQL Database:** Persistent storage for analysis history
- **Session-Based History:** Tracks past analyses per user via cookie-based sessions
- **Drag & Drop Upload:** Intuitive PDF file upload
- **Responsive UI:** Clean, modern single-page interface

## Quick Start

```bash
cp .env.example .env
# Edit .env and add your GIGACHAT_CREDENTIALS and DB_PASSWORD

docker-compose up -d --build
```

Open `http://localhost:8001` (note: port 8001 to avoid conflict with original)

## Architecture

- **Frontend:** Single HTML page with vanilla JS (enhanced slide-by-slide display)
- **Backend:** FastAPI (async)
- **Database:** PostgreSQL 15
- **LLM:** GigaChat-2-Pro (Sberbank)
- **PDF Processing:** PyMuPDF (converts PDF to individual slide images)
- **ORM:** SQLAlchemy (async)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve the HTML frontend |
| POST | `/analyze` | Upload a PDF, get full presentation feedback (slide-by-slide) |
| POST | `/improve` | Improve by aspect (`priority`) or by reference (`reference_file`) |
| POST | `/save` | Save analysis result to database |
| GET | `/history` | Get last 10 analyses for current session |

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GIGACHAT_CREDENTIALS` | GigaChat base64 authorization credentials | Yes |
| `GIGACHAT_MODEL` | Model to use (default: `GigaChat-2-Pro`) | No |
| `DATABASE_URL` | PostgreSQL async connection string | Yes |
| `DB_PASSWORD` | Database password | Yes |
| `MAX_FILE_SIZE` | Max upload size in bytes (default: 20971520) | No |
| `MAX_PDF_PAGES` | Max PDF pages to process (default: 20) | No |
| `SLIDE_BY_SLIDE` | Enable slide-by-slide processing (default: true) | No |

## How Slide-by-Slide Works

1. **PDF → Individual Images:** Each page is extracted as a separate JPEG image
2. **Per-Slide Analysis:** Each slide is sent to GigaChat with a specific prompt
3. **Structured Response:** Each slide returns:
   - `feedback`: Detailed analysis for that specific slide
   - `strengths`: Array of strong points
   - `weaknesses`: Array of weak points
   - `suggestions`: Array of concrete improvement suggestions
4. **Overall Assessment:** After all slides are analyzed, a summary is generated
5. **UI Display:** Each slide's feedback is shown in a card with color-coded tags

## Troubleshooting

**Issue: `GIGACHAT_CREDENTIALS is not set` error**
- Ensure your `.env` file contains valid GigaChat credentials (base64 format)

**Issue: Database connection refused**
- Check that the PostgreSQL container is running: `docker-compose ps`
- Verify `DB_PASSWORD` matches in both `.env` and `docker-compose.yml`

**Issue: SSL certificate error**
- SSL verification is disabled by default (`verify_ssl_certs=False`) for university VM

**Issue: Analysis takes too long**
- Slide-by-slide mode makes multiple API calls (one per slide)
- This is expected behavior; you can disable it by setting `SLIDE_BY_SLIDE=false`

## Stop All Services

```bash
docker-compose down -v  # -v removes the database volume
```

## License

MIT License — see the [LICENSE](LICENSE) file for details.
