# SlideWise — AI-анализ и улучшение презентаций

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)
![GigaChat](https://img.shields.io/badge/AI-GigaChat--2--Pro-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

AI-powered presentation analysis with persistent history. Upload a PDF presentation and get instant, detailed feedback on content, design, and actionable improvement tips.

## Features

- **Full Presentation Analysis:** Upload a complete PDF (up to 20 pages), not just one slide
- **4 Improvement Modes:** Visual clarity, conciseness, colorful design, logical clarity
- **Reference Imitation:** Make your presentation similar to a reference example
- **PostgreSQL Database:** Persistent storage for analysis history
- **Session-Based History:** Tracks past analyses per user via cookie-based sessions
- **Drag & Drop Upload:** Intuitive PDF file upload
- **Responsive UI:** Clean, modern single-page interface in Russian

## Quick Start

```bash
cp .env.example .env
# Edit .env and add your GIGACHAT_CREDENTIALS and DB_PASSWORD

docker-compose up -d --build
```

Open `http://localhost:8000`

## Architecture

- **Frontend:** Single HTML page with vanilla JS
- **Backend:** FastAPI (async)
- **Database:** PostgreSQL 15
- **LLM:** GigaChat-2-Pro (Sberbank)
- **PDF Processing:** PyMuPDF (converts PDF to stitched image)
- **ORM:** SQLAlchemy (async)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve the HTML frontend |
| POST | `/analyze` | Upload a PDF, get full presentation feedback |
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

## Troubleshooting

**Issue: `GIGACHAT_CREDENTIALS is not set` error**
- Ensure your `.env` file contains valid GigaChat credentials (base64 format)

**Issue: Database connection refused**
- Check that the PostgreSQL container is running: `docker-compose ps`
- Verify `DB_PASSWORD` matches in both `.env` and `docker-compose.yml`

**Issue: SSL certificate error**
- SSL verification is disabled by default (`verify_ssl_certs=False`) for university VM

## Stop All Services

```bash
docker-compose down -v  # -v removes the database volume
```

## License

MIT License — see the [LICENSE](LICENSE) file for details.
