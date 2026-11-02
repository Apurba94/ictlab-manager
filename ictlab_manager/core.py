"""Computer lab rules, with dates and times passed in so they can be tested."""
from datetime import date, datetime, timedelta

PRIORITY_HOURS = {"urgent": 4, "high": 24, "normal": 72, "low": 168}
STATUSES = ("working", "faulty", "in repair", "retired")


def parse_time(text):
    for f in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, f)
        except ValueError:
            pass
    raise ValueError(f"not a date and time: {text}")


def overlaps(a_start, a_end, b_start, b_end):
    """Two bookings clash if each starts before the other ends. Back-to-back bookings do not clash."""
    return a_start < b_end and b_start < a_end


def check_booking(start, end, existing, opening=(8, 18), now=None):
    """Return the reasons a booking cannot go ahead. existing: list of (start, end, who)."""
    problems = []
    if end <= start:
        problems.append("the end must be after the start")
        return problems
    if start.date() != end.date():
        problems.append("a booking must stay within one day")
    if start.hour < opening[0] or (end.hour, end.minute) > (opening[1], 0):
        problems.append(f"the lab is open {opening[0]}:00 to {opening[1]}:00")
    if now is not None and start < now:
        problems.append("that time has passed")
    for s, e, who in existing:
        if overlaps(start, end, s, e):
            problems.append(f"clashes with {who}, {s:%H:%M} to {e:%H:%M}")
    return problems


def free_slots(day, existing, opening=(8, 18), minimum=30):
    """Gaps in a day's bookings, for offering other times."""
    start = datetime(day.year, day.month, day.day, opening[0])
    end = datetime(day.year, day.month, day.day, opening[1])
    out, cursor = [], start
    for s, e in sorted((s, e) for s, e, _ in existing):
        if s > cursor and (s - cursor).total_seconds() >= minimum * 60:
            out.append((cursor, s))
        cursor = max(cursor, e)
    if end > cursor and (end - cursor).total_seconds() >= minimum * 60:
        out.append((cursor, end))
    return out


def ticket_due(priority, opened):
    if priority not in PRIORITY_HOURS:
        raise ValueError(f"unknown priority {priority}")
    return opened + timedelta(hours=PRIORITY_HOURS[priority])


def ticket_state(priority, opened, closed, now):
    due = ticket_due(priority, opened)
    if closed:
        return "closed in time" if closed <= due else "closed late"
    return "overdue" if now > due else "open"


def sla_report(tickets, now):
    """tickets: list of (priority, opened, closed or None). Share closed in time, and mean hours to fix."""
    done = [t for t in tickets if t[2]]
    in_time = sum(1 for t in done if t[2] <= ticket_due(t[0], t[1]))
    return {"open": len(tickets) - len(done), "overdue": sum(1 for t in tickets if ticket_state(t[0], t[1], t[2], now) == "overdue"), "in_time": in_time / len(done) if done else None, "mean_hours": sum((t[2] - t[1]).total_seconds() for t in done) / 3600 / len(done) if done else None}


def next_due(last, every_days, today):
    """The next maintenance date. Never-serviced devices are due today."""
    if last is None:
        return today
    return last + timedelta(days=every_days)


def maintenance_list(devices, today, warn_days=14):
    """devices: list of (name, last date or None, every days). Returns (name, due date, overdue days), soonest first."""
    rows = []
    for name, last, every in devices:
        due = next_due(last, every, today)
        if (due - today).days <= warn_days:
            rows.append((name, due, max(0, (today - due).days)))
    return sorted(rows, key=lambda r: r[1])


def licence_state(expires, seats, used, today, warn_days=60):
    out = []
    if expires:
        if expires < today:
            out.append("expired")
        elif (expires - today).days <= warn_days:
            out.append(f"expires in {(expires - today).days} days")
    if used > seats:
        out.append(f"{used - seats} seats over the limit")
    return out or ["ok"]


def fault_rate(faults, device_days):
    """Faults per 100 device-days, for comparing models fairly."""
    return faults / device_days * 100 if device_days else 0.0


def worst_devices(fault_counts, age_days, limit=5):
    """Rank devices by faults per year of life, with at least 30 days of history."""
    rows = []
    for name, n in fault_counts.items():
        age = max(age_days.get(name, 0), 30)
        rows.append((name, n, n / age * 365))
    return sorted(rows, key=lambda r: -r[2])[:limit]
