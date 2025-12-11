<div align="center">

# MicroMusicBlog API

FastAPI-powered microblog backend for posts, comments, likes, and file attachments with JWT auth, Redis caching, and async I/O.

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121%2B-009485?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-Unspecified-lightgrey)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-0db7ed?logo=docker)](https://www.docker.com/)

</div>

## Tech Stack & Features
- **Stack**: FastAPI, PostgreSQL (SQLAlchemy + asyncpg), Redis, Alembic, Pydantic, Docker, Pytest.
- **JWT auth**: Access/refresh tokens with OAuth2 password flow and token-type validation.
- **High performance**: Redis-backed caching with stampede protection and cache invalidation hooks.
- **Background/async tasks**: Non-blocking file uploads for posts/avatars; async cache invalidation off the request path.
- **Robust errors**: Global HTTP and fallback exception handlers with structured JSON responses.
- **Testing**: Pytest + pytest-asyncio fixtures covering auth, users, posts, comments, likes, status.

## Project Structure
```
.
├── app/
│   ├── main.py                # FastAPI app, CORS, exception handlers
│   ├── config.py              # Pydantic settings
│   ├── database.py            # Async SQLAlchemy engine/session
│   ├── redis_client.py        # Redis init/teardown
│   ├── cache.py               # Cache helpers + stampede protection
│   ├── events.py              # Cache invalidation hooks
│   ├── oauth2.py              # JWT utilities and auth dependency
│   ├── models.py              # ORM models (users, posts, comments, files, likes)
│   ├── routers/               # auth, user, post, comment, like, status
│   ├── schemas.py             # Pydantic schemas
│   ├── utils.py               # Password hashing/verification
│   └── tests/                 # Pytest suites for core flows
├── alembic/                   # Database migrations
├── docker-compose.yml         # Local orchestration (API, Postgres, Redis)
├── Dockerfile                 # API image
├── requirements.txt
└── start.sh
```

## Getting Started
### Prerequisites
- Docker + Docker Compose
- Python 3.13 (for local development)


### Run with Docker (recommended)
```bash
cp .env.example .env    # if not present, create .env manually using the table below
docker-compose up --build
# App will be available at http://localhost:8000
```

### Local Development
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

# Set env vars (see table) or create a .env file
alembic upgrade head

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables
| Variable | Description | Default / Example |
| --- | --- | --- |
| `DATABASE_HOSTNAME` | PostgreSQL host | `localhost` |
| `DATABASE_PORT` | PostgreSQL port | `5432` |
| `DATABASE_NAME` | Database name | `blog` |
| `DATABASE_USER` | Database user | `postgres` |
| `DATABASE_PASSWORD` | Database password | `postgres` |
| `SECRET_KEY` | JWT signing secret | _required_ |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime (minutes) | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime (days) | `7` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `REDIS_MAX_CONNECTIONS` | Max Redis connections | `30` |
| `CACHE_TTL` | Cache TTL (seconds) | `300` |

## API Documentation
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Running Tests
```bash
docker-compose exec api python -m pytest
# or locally (venv active)
pytest
```

