# PostgreSQL Infrastructure Notes

This project provides local infrastructure via `docker-compose.postgres.yml`:
- PostgreSQL 16
- pgAdmin 4

## Quick Start
1. Copy `.env.postgres.example` to `.env.postgres` and set secure passwords.
2. Start services:
   ```bash
   docker compose --env-file .env.postgres -f docker-compose.postgres.yml up -d
   ```
3. Point app to Postgres with `DATABASE_URL` or `.streamlit/secrets.toml` `[database].url`.

## pgAdmin Connection
- Host: `postgres` (from docker network) or `localhost`
- Port: `5432`
- Database: `pystreamline`
- User: `pystreamline_app`

## Data Migration
Use:
```bash
python scripts/migrate_sqlite_to_postgres.py --sqlite-path users.db --truncate
```
