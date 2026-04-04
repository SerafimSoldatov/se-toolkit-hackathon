# SlideWise — Version 2 (Database + History)

AI-powered slide analysis with persistent history using PostgreSQL.

## Features

- All Version 1 features
- PostgreSQL database for persistent storage
- Session-based history (last 5 analyses)
- Cookie-based session tracking
- Fire-and-forget database saves (non-blocking)

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
git clone <repo-url>
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

Access at `http://<VM_IP>:8000`

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
