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
4. Store OpenAI key in DB settings:
   ```sql
   INSERT INTO app_settings (setting_key, setting_value, created_at, updated_at)
   VALUES ('OPENAI_API_KEY', 'your_key_here', NOW()::text, NOW()::text)
   ON CONFLICT (setting_key)
   DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at;
   ```

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

To move an existing Postgres database to Supabase:
```powershell
$env:SOURCE_DATABASE_URL="postgresql://pystreamline_app:YOUR_LOCAL_PASSWORD@localhost:5432/pystreamline"
$env:TARGET_DATABASE_URL="postgresql://postgres.dlbeyfzfubkiqklaowbd:YOUR_SUPABASE_PASSWORD@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require"
python scripts/migrate_postgres_to_postgres.py --truncate
```
