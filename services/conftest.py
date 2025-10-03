import os
from pathlib import Path

TEST_DB = os.getenv("TEST_DATABASE_PATH", "/tmp/trading_bot_tests.db")
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{TEST_DB}")
os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")

from sqlalchemy import create_engine  # noqa: E402

from libs.db import db  # noqa: E402

connect_args = (
    {"check_same_thread": False} if os.environ["DATABASE_URL"].startswith("sqlite") else {}
)

if str(db.engine.url) != os.environ["DATABASE_URL"]:
    db.engine.dispose()
    new_engine = create_engine(os.environ["DATABASE_URL"], future=True, connect_args=connect_args)
    db.engine = new_engine
    db.SessionLocal.configure(bind=new_engine)

# Ensure database file exists
if os.environ["DATABASE_URL"].startswith("sqlite"):
    Path(TEST_DB).touch()

from infra import (  # noqa: E402
    AuditBase,
    EntitlementsBase,
    MarketplaceBase,
    ScreenerBase,
    SocialBase,
    TradingBase,
)

EntitlementsBase.metadata.create_all(bind=db.engine)
ScreenerBase.metadata.create_all(bind=db.engine)
MarketplaceBase.metadata.create_all(bind=db.engine)
SocialBase.metadata.create_all(bind=db.engine)
AuditBase.metadata.create_all(bind=db.engine)
TradingBase.metadata.drop_all(bind=db.engine)
TradingBase.metadata.create_all(bind=db.engine)
