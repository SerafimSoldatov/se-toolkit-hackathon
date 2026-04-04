# SlideWise — Version 2 (Database + History)

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

AI-powered slide analysis with persistent history using PostgreSQL. Upload a slide (JPG, PNG, or PDF) and get instant, detailed feedback on content, design, and actionable tips.

## Screenshots

> _Add screenshots here showing the UI in action. Recommended:_
> - `screenshots/upload.png` — Initial upload screen
> - `screenshots/results.png` — Analysis results displayed
> - `screenshots/history.png` — History panel with past analyses

## Features

- **AI-Powered Analysis:** Uses Groq's Llama 3.2 Vision model to analyze slide content and design
- **PostgreSQL Database:** Persistent storage for analysis history
- **Session-Based History:** Tracks last 5 analyses per user via cookie-based sessions
- **Fire-and-Forget Saves:** Non-blocking database writes don't slow down responses
- **Drag & Drop Upload:** Intuitive file upload with image preview
- **File Validation:** Supports JPG, PNG, and PDF up to 5MB
- **Responsive UI:** Clean, modern single-page interface

## Quick Start

### Local Development

```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY and DB_PASSWORD

docker-compose up -d --build
```

Open `http://localhost:8000`

### Without Docker (local PostgreSQL)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Deployment on Ubuntu 24.04 VM

### 1. Install Docker

```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect
```

### 2. Clone and configure

```bash
git clone https://github.com/inno-se-toolkit/se-toolkit-hackathon/blob/main/README.md
cd version_2
cp .env.example .env
nano .env  # fill in GROQ_API_KEY and DB_PASSWORD
```

### 3. Open firewall port

```bash
sudo ufw allow 8000
```

### 4. Run

```bash
docker-compose up -d --build
```

Access at `http:10.93.26.141//:8000`

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve the HTML page |
| POST | `/analyze` | Upload an image, get JSON feedback |
| GET | `/history` | Get last 5 analyses for current session |

## Architecture

- **Frontend:** Single HTML page with vanilla JS
- **Backend:** FastAPI (async)
- **Database:** PostgreSQL 15
- **LLM:** Groq API (Llama 3.2 Vision)
- **ORM:** SQLAlchemy (async)
- **Session:** Cookie-based session_id

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GROQ_API_KEY` | Groq API key for LLM access | Yes |
| `GROQ_MODEL` | Model to use (default: `llama-3.2-90b-vision-preview`) | No |
| `DATABASE_URL` | PostgreSQL async connection string | Yes |
| `DB_PASSWORD` | Database password | Yes |
| `MAX_FILE_SIZE` | Max upload size in bytes (default: 5242880) | No |

## Update & Restart

```bash
git pull
docker-compose down
docker-compose up -d --build
```

## Stop All Services

```bash
docker-compose down -v  # -v removes the database volume
```

## Troubleshooting

### Common Issues

**Issue: `GROQ_API_KEY is not set` error**
- Ensure your `.env` file contains a valid Groq API key
- Get one at [https://console.groq.com](https://console.groq.com)
- Run `docker-compose restart backend` after updating

**Issue: Database connection refused**
- Check that the PostgreSQL container is running: `docker-compose ps`
- Verify `DB_PASSWORD` matches in both `.env` and `docker-compose.yml`
- Wait for the DB health check to pass before the backend starts

**Issue: `File too large` error**
- The default limit is 5MB. Increase it by setting `MAX_FILE_SIZE` in `.env`

**Issue: Analysis times out**
- Groq API may be slow during peak usage. The default timeout is 30 seconds
- Check Groq API status and your rate limits at [https://console.groq.com](https://console.groq.com)

**Issue: Port 8000 already in use**
- Change the port mapping in `docker-compose.yml`: `"8001:8000"`
- Or stop the conflicting service: `sudo lsof -i :8000`

**Issue: Docker permission denied**
- Run `sudo usermod -aG docker $USER` and log out/in
- Or prefix commands with `sudo`

### Viewing Logs

```bash
docker-compose logs -f backend   # Backend logs
docker-compose logs -f db        # Database logs
```

### Database Reset

```bash
docker-compose down -v
docker-compose up -d --build
```

## Contributing

Contributions are welcome! Here's how you can help:

1. **Fork the repository**
2. **Create a feature branch:** `git checkout -b feature/your-feature-name`
3. **Make your changes**
4. **Test locally:** Ensure the app runs with `docker-compose up -d --build`
5. **Commit your changes:** `git commit -m "Add your feature"`
6. **Push to the branch:** `git push origin feature/your-feature-name`
7. **Open a Pull Request**

### Development Guidelines

- Follow [PEP 8](https://peps.python.org/pep-0008/) for Python code
- Use async/await patterns consistently
- Add logging for errors (see `logging.basicConfig` in `main.py`)
- Test with both Docker and local PostgreSQL

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 SerafimSoldatov
