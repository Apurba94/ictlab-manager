"""The offline web app."""
from datetime import date, datetime

from . import core
from .fieldkit import App, Fail, Raw, bar_chart, card, download, form, h, link, redirect, stats, table

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (id INTEGER PRIMARY KEY, tag TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, model TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'working', added TEXT NOT NULL, last_service TEXT, every_days INTEGER NOT NULL DEFAULT 180);
CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY, who TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT '', start TEXT NOT NULL, end TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY, device INTEGER REFERENCES devices(id), problem TEXT NOT NULL, priority TEXT NOT NULL, opened TEXT NOT NULL, closed TEXT, fix TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS licences (id INTEGER PRIMARY KEY, name TEXT NOT NULL, seats INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0, expires TEXT);
"""


def create_app(db="ictlab.db", clock=datetime.now):
    a = App("ICT Lab Manager", db, SCHEMA, [("Today", "/"), ("Devices", "/devices"), ("Bookings", "/bookings"), ("Faults", "/tickets"), ("Licences", "/licences")])

    def now():
        return clock().replace(second=0, microsecond=0)

    def day_bookings(d):
        return [(core.parse_time(r["start"]), core.parse_time(r["end"]), r["who"]) for r in a.rows("SELECT * FROM bookings WHERE substr(start, 1, 10) = ? ORDER BY start", d)]

    def maintenance():
        return core.maintenance_list([(r["tag"], date.fromisoformat(r["last_service"]) if r["last_service"] else None, r["every_days"]) for r in a.rows("SELECT * FROM devices WHERE status != 'retired'")], now().date())

    def ticket_rows():
        return [(r["priority"], core.parse_time(r["opened"]), core.parse_time(r["closed"]) if r["closed"] else None) for r in a.rows("SELECT * FROM tickets")]

    @a.route("/")
    def home(req):
        n = now()
        s = core.sla_report(ticket_rows(), n)
        counts = a.rows("SELECT status, COUNT(*) c FROM devices GROUP BY status")
        today_rows = [{"s": x, "e": y, "w": w} for x, y, w in day_bookings(n.date().isoformat())]
        body = stats([("Devices", a.one("SELECT COUNT(*) FROM devices WHERE status != 'retired'")), ("Open faults", s["open"]), ("Overdue faults", s["overdue"]), ("Service due", len(maintenance()))])
        body += card("Today's bookings", table(today_rows, [("From", lambda r: f"{r['s']:%H:%M}"), ("To", lambda r: f"{r['e']:%H:%M}"), ("Who", "w")], "No bookings today."))
        body += card("Device status", bar_chart([(r["status"], r["c"]) for r in counts]))
        body += card("Service due soon", table(maintenance(), [("Device", lambda r: r[0]), ("Due", lambda r: r[1].isoformat()), ("Days overdue", lambda r: r[2])], "Nothing due."))
        return a.page("Today", body)

    @a.route("/devices", ("GET", "POST"))
    def devices(req):
        if req.method == "POST":
            a.run("INSERT INTO devices (tag, kind, model, added, every_days) VALUES (?, ?, ?, ?, ?)", req.text("tag"), req.text("kind"), req.text("model", False), now().date().isoformat(), int(req.number("every_days", 180, 1, 3650)))
            return redirect("/devices")
        return a.page("Devices", card("Add a device", form(a, "/devices", [("tag", "Asset tag"), ("kind", "Kind", "select", [(k, k) for k in ("Desktop", "Laptop", "Projector", "Printer", "Router", "Tablet", "Other")]), ("model", "Model"), ("every_days", "Service every (days)", "number", 180)], "Add")) + card("All devices", table(a.rows("SELECT * FROM devices ORDER BY tag"), [("Tag", lambda r: link(f"/device/{r['id']}", r["tag"])), ("Kind", "kind"), ("Model", "model"), ("Status", "status"), ("Last service", "last_service")])) + '<p><a href="/devices.csv">Download CSV</a></p>')

    @a.route("/devices.csv")
    def devices_csv(req):
        rows = a.rows("SELECT tag, kind, model, status, added, last_service FROM devices ORDER BY tag")
        return download(rows, ["tag", "kind", "model", "status", "added", "last_service"], "devices.csv")

    @a.route("/device/<id>", ("GET", "POST"))
    def device(req, id):
        d = a.row("SELECT * FROM devices WHERE id = ?", id)
        if d is None:
            raise Fail("No such device", 404)
        if req.method == "POST":
            if req.get("action") == "service":
                a.run("UPDATE devices SET last_service = ? WHERE id = ?", now().date().isoformat(), id)
            else:
                status = req.text("status")
                if status not in core.STATUSES:
                    raise Fail("Unknown status")
                a.run("UPDATE devices SET status = ? WHERE id = ?", status, id)
            a.log("device", f"{d['tag']} {req.get('action') or req.get('status')}")
            return redirect(f"/device/{id}")
        tickets = a.rows("SELECT * FROM tickets WHERE device = ? ORDER BY id DESC", id)
        return a.page(d["tag"], stats([("Status", d["status"]), ("Faults", len(tickets))]) + card("Change status", form(a, f"/device/{id}", [("status", "Status", "select", [(s, s) for s in core.STATUSES])], "Save")) + card("Record a service", form(a, f"/device/{id}", [("action", "", "hidden", "service")], "Serviced today")) + card("Fault history", table(tickets, [("Opened", "opened"), ("Problem", "problem"), ("Fix", "fix")], "No faults recorded.")))

    @a.route("/bookings", ("GET", "POST"))
    def bookings(req):
        n = now()
        if req.method == "POST":
            d = req.date("day")
            try:
                s, e = core.parse_time(f"{d}T{req.text('start')}"), core.parse_time(f"{d}T{req.text('end')}")
            except ValueError as exc:
                raise Fail(str(exc)) from None
            existing = day_bookings(d)
            problems = core.check_booking(s, e, existing, now=n)
            if problems:
                free = ", ".join(f"{x:%H:%M} to {y:%H:%M}" for x, y in core.free_slots(s.date(), existing))
                raise Fail("; ".join(problems) + (f". Free times: {free}" if free else ""))
            a.run("INSERT INTO bookings (who, purpose, start, end) VALUES (?, ?, ?, ?)", req.text("who"), req.text("purpose", False), s.isoformat(timespec="minutes"), e.isoformat(timespec="minutes"))
            return redirect("/bookings")
        rows = a.rows("SELECT * FROM bookings WHERE substr(end, 1, 16) >= ? ORDER BY start", n.isoformat(timespec="minutes"))
        return a.page("Bookings", card("Book the lab", form(a, "/bookings", [("who", "Who"), ("purpose", "Purpose"), ("day", "Day", "date"), ("start", "Start", "time"), ("end", "End", "time")], "Book")) + card("Coming up", table(rows, [("Start", "start"), ("End", "end"), ("Who", "who"), ("Purpose", "purpose")], "No bookings.")))

    @a.route("/tickets", ("GET", "POST"))
    def tickets(req):
        n = now()
        if req.method == "POST":
            if req.get("close"):
                cur = a.run("UPDATE tickets SET closed = ?, fix = ? WHERE id = ? AND closed IS NULL", n.isoformat(timespec="minutes"), req.text("fix"), req.text("close"))
                if cur.rowcount == 0:
                    raise Fail("That fault is already closed", 409)
            else:
                device = req.text("device", False) or None
                priority = req.text("priority")
                if priority not in core.PRIORITY_HOURS:
                    raise Fail("Unknown priority")
                a.run("INSERT INTO tickets (device, problem, priority, opened) VALUES (?, ?, ?, ?)", device, req.text("problem"), priority, n.isoformat(timespec="minutes"))
                if device:
                    a.run("UPDATE devices SET status = 'faulty' WHERE id = ? AND status = 'working'", device)
            return redirect("/tickets")
        rows = a.rows("SELECT t.*, d.tag FROM tickets t LEFT JOIN devices d ON d.id = t.device ORDER BY t.closed IS NOT NULL, t.id DESC")
        s = core.sla_report(ticket_rows(), n)
        opts = [("", "No device")] + [(r["id"], r["tag"]) for r in a.rows("SELECT id, tag FROM devices ORDER BY tag")]

        def state(r):
            st = core.ticket_state(r["priority"], core.parse_time(r["opened"]), core.parse_time(r["closed"]) if r["closed"] else None, n)
            return Raw(f'<span class="{"bad" if st in ("overdue", "closed late") else "good" if st == "closed in time" else ""}">{st}</span>')
        body = stats([("Open", s["open"]), ("Overdue", s["overdue"]), ("Fixed in time", "n/a" if s["in_time"] is None else f"{s['in_time']:.0%}"), ("Mean hours to fix", "n/a" if s["mean_hours"] is None else f"{s['mean_hours']:.1f}")])
        body += card("Report a fault", form(a, "/tickets", [("device", "Device", "select", opts), ("problem", "Problem", "textarea"), ("priority", "Priority", "select", [(p, p) for p in core.PRIORITY_HOURS])], "Report"))
        body += card("Faults", table(rows, [("#", "id"), ("Device", "tag"), ("Problem", "problem"), ("Priority", "priority"), ("State", state)], "No faults."))
        body += card("Close a fault", form(a, "/tickets", [("close", "Fault number", "number"), ("fix", "What fixed it")], "Close"))
        return a.page("Faults", body)

    @a.route("/licences", ("GET", "POST"))
    def licences(req):
        if req.method == "POST":
            a.run("INSERT INTO licences (name, seats, used, expires) VALUES (?, ?, ?, ?)", req.text("name"), int(req.number("seats", low=0)), int(req.number("used", 0, 0)), req.date("expires", False) or None)
            return redirect("/licences")
        today = now().date()
        return a.page("Licences", card("Add a licence", form(a, "/licences", [("name", "Software"), ("seats", "Seats", "number"), ("used", "In use", "number", 0), ("expires", "Expires", "date")], "Add")) + card("Licences", table(a.rows("SELECT * FROM licences ORDER BY name"), [("Software", "name"), ("Seats", "seats"), ("In use", "used"), ("Expires", "expires"), ("State", lambda r: "; ".join(core.licence_state(date.fromisoformat(r["expires"]) if r["expires"] else None, r["seats"], r["used"], today)))])))

    return a
