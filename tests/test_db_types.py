"""Values must fit the schema on strict servers (MySQL), not only on SQLite, which ignores lengths."""
from datetime import datetime, timedelta, timezone

from app.models import DateTime, ScheduleOption
from sqlalchemy.dialects import mysql, sqlite


def test_review_status_column_fits_every_status():
    for status in ("approved", "checks_passed_with_warnings", "flagged", "rejected", "pending"):
        assert len(status) <= ScheduleOption.__table__.c.review_status.type.length


def test_total_credits_keeps_fractional_credits():
    assert ScheduleOption.__table__.c.total_credits.type.python_type is float


def test_datetime_round_trips_as_aware_utc_on_mysql_and_sqlite():
    t = DateTime()
    local = datetime(2026, 11, 5, 14, 30, 0, 123456, tzinfo=timezone(timedelta(hours=-5)))
    stored = t.process_bind_param(local, mysql.dialect())
    assert stored.tzinfo is None and stored.hour == 19 and stored.microsecond == 123456
    assert t.process_result_value(stored, mysql.dialect()) == local
    assert t.process_result_value(stored, mysql.dialect()).tzinfo == timezone.utc
    assert t.process_result_value(t.process_bind_param(local, sqlite.dialect()), sqlite.dialect()) == local
    assert "DATETIME(fsp=6)" in repr(t.load_dialect_impl(mysql.dialect())) or t.load_dialect_impl(mysql.dialect()).fsp == 6
