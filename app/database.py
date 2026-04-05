from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import DATABASE_URL

engine = None
async_session = None


def init_db():
    """Initialize database engine and session factory."""
    global engine, async_session
    if not DATABASE_URL:
        return
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """Dependency that yields a database session."""
    if async_session is None:
        init_db()
    async with async_session() as session:
        yield session


class Base(DeclarativeBase):
    pass
