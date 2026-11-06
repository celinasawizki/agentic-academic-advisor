from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _sqlite else {},
    # Remote servers (e.g. Temple's dataanalytics MySQL) close idle connections; test and recycle them.
    **({} if _sqlite else {"pool_pre_ping": True, "pool_recycle": 280}),
    # InnoDB's default REPEATABLE READ takes gap locks on `DELETE ... WHERE plan_id = ?`; agents of
    # concurrent plans then deadlock on the following INSERTs (error 1213). READ COMMITTED takes none.
    **({"isolation_level": "READ COMMITTED"} if settings.database_url.startswith("mysql") else {}),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
