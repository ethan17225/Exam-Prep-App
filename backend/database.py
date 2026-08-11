from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mcq_app")

engine = create_engine(
    DATABASE_URL,
    # Routes are sync `def`, so they run on the ~40-thread threadpool. The default
    # pool of 5+10 meant the 16th concurrent request blocked 30s and then 500'd.
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
    # Postgres restarts and idle-connection reapers otherwise surface as a 500 on
    # the first request to reuse a dead connection.
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Leave no half-applied transaction on the connection when it returns to
        # the pool — a later request must not inherit it.
        db.rollback()
        raise
    finally:
        db.close()
