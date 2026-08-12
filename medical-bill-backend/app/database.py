from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Detect database type from the URL
_IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")

if _IS_SQLITE:
    # SQLite requires special connection args for async + threading
    engine: AsyncEngine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )
else:
    engine: AsyncEngine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables in the database."""
    async with engine.begin() as conn:
        # Import models so they are registered with SQLModel.metadata
        from app import models  # noqa: F401
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncSession:
    """Dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session