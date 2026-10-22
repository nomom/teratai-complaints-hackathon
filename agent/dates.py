"""Owner: A. Turn a date phrase (English or Malay) into a date range, counted from the complaint's received time.

    resolve_dates("hari Selasa lepas", received) -> DateRange(start=2026-08-18, end=2026-08-18, exact=True)

First pass: covers the common phrases. TODO(A): grow this from the training complaints that fail to match
(run `python -m scripts.run_batch --split train` and read the NO_MATCH flags).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

WINDOW_DAYS = 45

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "isnin": 0, "selasa": 1, "rabu": 2, "khamis": 3, "jumaat": 4, "sabtu": 5, "ahad": 6,
}
MONTHS = {
    "january": 1, "jan": 1, "januari": 1, "february": 2, "feb": 2, "februari": 2, "march": 3, "mar": 3, "mac": 3,
    "april": 4, "apr": 4, "may": 5, "mei": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "julai": 7,
    "august": 8, "aug": 8, "ogos": 8, "september": 9, "sep": 9, "sept": 9, "october": 10, "oct": 10, "oktober": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12, "disember": 12,
}
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))


@dataclass
class DateRange:
    start: dt.date
    end: dt.date
    exact: bool          # True when the phrase pins a specific day
    rule: str            # which rule fired, for the trace

    def contains(self, day: dt.date) -> bool:
        return self.start <= day <= self.end


def resolve_dates(phrase: str, received: dt.datetime) -> DateRange:
    p = (phrase or "").lower()
    today = received.date()

    def day(d, rule):
        return DateRange(d, d, True, rule)

    # Explicit date: "15 September 2026", "15 Sep", "15/9/2026"
    m = re.search(rf"\b(\d{{1,2}})\s+({_MONTH_RE})\b(?:\s+(\d{{4}}))?", p)
    if m:
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            d = dt.date(year, MONTHS[m.group(2)], int(m.group(1)))
            if d > today:
                d = d.replace(year=year - 1)
            return day(d, "explicit date")
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", p)
    if m:
        try:
            year = int(m.group(3)) if m.group(3) else today.year
            year = year + 2000 if year < 100 else year
            return day(dt.date(year, int(m.group(2)), int(m.group(1))), "numeric date")
        except ValueError:
            pass

    if re.search(r"\b(today|this morning|this afternoon|tonight|hari ini|pagi tadi|tadi)\b", p):
        return day(today, "today")
    if re.search(r"\b(day before yesterday|kelmarin|two days ago|2 days ago|dua hari lepas)\b", p):
        return day(today - dt.timedelta(days=2), "two days ago")
    if re.search(r"\b(yesterday|semalam)\b", p):
        return day(today - dt.timedelta(days=1), "yesterday")

    # "last Tuesday", "on Tuesday", "hari Selasa lepas", "Selasa lepas": the most recent such day before today
    for name, wd in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", p):
            back = (today.weekday() - wd) % 7 or 7
            return day(today - dt.timedelta(days=back), f"last {name}")

    m = re.search(r"\b(\d+|a|one|two|three|satu|dua|tiga)\s+(days?|hari)\s+(ago|lepas|lalu)\b", p)
    if m:
        n = {"a": 1, "one": 1, "satu": 1, "two": 2, "dua": 2, "three": 3, "tiga": 3}.get(m.group(1)) or int(m.group(1))
        return day(today - dt.timedelta(days=n), "n days ago")

    if re.search(r"\b(last week|minggu lepas|minggu lalu)\b", p):
        return DateRange(today - dt.timedelta(days=14), today - dt.timedelta(days=1), False, "last week")
    if re.search(r"\b(this week|minggu ini)\b", p):
        return DateRange(today - dt.timedelta(days=today.weekday()), today, False, "this week")

    # Month only ("in June", "bulan Jun"): useful for fee disputes
    m = re.search(rf"\b({_MONTH_RE})\b", p)
    if m:
        mon = MONTHS[m.group(1)]
        year = today.year if mon <= today.month else today.year - 1
        start = dt.date(year, mon, 1)
        end = (dt.date(year + (mon == 12), mon % 12 + 1, 1) - dt.timedelta(days=1))
        return DateRange(start, min(end, today), False, "month")

    return DateRange(today - dt.timedelta(days=WINDOW_DAYS + 1), today, False, "whole window")


def month_of(phrase: str, received: dt.datetime) -> str:
    """"Jun 2026" / "bulan Jun" -> "2026-06", or ""."""
    m = re.search(rf"\b({_MONTH_RE})\b(?:\s+(\d{{4}}))?", (phrase or "").lower())
    if not m:
        return ""
    mon = MONTHS[m.group(1)]
    year = int(m.group(2)) if m.group(2) else (received.year if mon <= received.month else received.year - 1)
    return f"{year}-{mon:02d}"
