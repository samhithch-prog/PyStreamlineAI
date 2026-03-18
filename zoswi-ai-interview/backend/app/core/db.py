from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import get_settings

settings = get_settings()


def _normalize_database_url(database_url: str) -> str:
    normalized = str(database_url or "").strip()

    # Render/Supabase often provide postgres:// or postgresql:// URLs.
    # This backend uses psycopg v3, so force the compatible SQLAlchemy driver.
    if normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql://", 1)
    if normalized.startswith("postgresql+psycopg2://"):
        normalized = normalized.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    elif normalized.startswith("postgresql://"):
        normalized = normalized.replace("postgresql://", "postgresql+psycopg://", 1)
    elif normalized.startswith("sqlite://") and not normalized.startswith("sqlite+aiosqlite://"):
        normalized = normalized.replace("sqlite://", "sqlite+aiosqlite://", 1)

    return normalized


engine = create_async_engine(
    _normalize_database_url(settings.database_url),
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await _run_lightweight_migrations(connection)


async def _run_lightweight_migrations(connection) -> None:
    dialect_name = str(connection.dialect.name).strip().lower()
    if dialect_name == "sqlite":
        pragma_result = await connection.execute(text("PRAGMA table_info(interview_sessions)"))
        columns = {str(row[1]) for row in pragma_result.fetchall()}
        if "interview_type" not in columns:
            await connection.execute(
                text("ALTER TABLE interview_sessions ADD COLUMN interview_type VARCHAR(32) NOT NULL DEFAULT 'mixed'")
            )
        if "owner_user_id" not in columns:
            await connection.execute(
                text("ALTER TABLE interview_sessions ADD COLUMN owner_user_id VARCHAR(128) NOT NULL DEFAULT ''")
            )
        if "org_id" not in columns:
            await connection.execute(
                text("ALTER TABLE interview_sessions ADD COLUMN org_id VARCHAR(128) NOT NULL DEFAULT ''")
            )
        if "domain" not in columns:
            await connection.execute(
                text("ALTER TABLE interview_sessions ADD COLUMN domain VARCHAR(64) NOT NULL DEFAULT ''")
            )
        return

    if dialect_name in {"postgresql", "postgres"}:
        # Ensure enum types exist for older Supabase databases that predate the current schema.
        await connection.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'interview_status') THEN
                        CREATE TYPE interview_status AS ENUM ('in_progress', 'completed');
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transcript_speaker') THEN
                        CREATE TYPE transcript_speaker AS ENUM ('ai', 'candidate', 'system');
                    END IF;
                END $$;
                """
            )
        )

        postgres_alter_statements = [
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS interview_type VARCHAR(32) NOT NULL DEFAULT 'mixed'",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(128) NOT NULL DEFAULT ''",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS org_id VARCHAR(128) NOT NULL DEFAULT ''",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS domain VARCHAR(64) NOT NULL DEFAULT ''",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS status interview_status NOT NULL DEFAULT 'in_progress'",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS current_question TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS turn_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS max_turns INTEGER NOT NULL DEFAULT 5",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS transcript_history JSONB NOT NULL DEFAULT '[]'::jsonb",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS evaluation_signals JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "ALTER TABLE interview_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        ]
        for statement in postgres_alter_statements:
            await connection.execute(text(statement))

        await connection.execute(
            text("CREATE INDEX IF NOT EXISTS idx_interview_sessions_owner_user_id ON interview_sessions(owner_user_id)")
        )
        await connection.execute(
            text("CREATE INDEX IF NOT EXISTS idx_interview_sessions_org_id ON interview_sessions(org_id)")
        )
