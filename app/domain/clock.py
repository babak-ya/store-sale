from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import jdatetime

TEHRAN = ZoneInfo("Asia/Tehran")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def accounting_date(at: datetime) -> str:
    if at.tzinfo is None:
        raise ValueError("An aware timestamp is required")
    return at.astimezone(TEHRAN).date().isoformat()


def jalali_date(at: datetime) -> str:
    if at.tzinfo is None:
        raise ValueError("An aware timestamp is required")
    return jdatetime.date.fromgregorian(date=at.astimezone(TEHRAN).date()).strftime("%Y/%m/%d")
