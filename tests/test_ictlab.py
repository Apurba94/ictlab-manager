import random
import unittest
from datetime import date, datetime, timedelta

from ictlab_manager import core, create_app
from ictlab_manager.core import check_booking, fault_rate, free_slots, licence_state, maintenance_list, next_due, overlaps, parse_time, sla_report, ticket_due, ticket_state, worst_devices

T = datetime(2026, 11, 3, 9)


def at(h, m=0, d=3):
    return datetime(2026, 11, d, h, m)


class TestBookings(unittest.TestCase):
    def test_overlap_cases(self):
        self.assertTrue(overlaps(at(9), at(11), at(10), at(12)))
        self.assertTrue(overlaps(at(9), at(12), at(10), at(11)))
        self.assertFalse(overlaps(at(9), at(10), at(10), at(11)))

    def test_overlap_agrees_with_checking_every_minute(self):
        rng = random.Random(1)
        for _ in range(500):
            a, b = sorted(rng.sample(range(100), 2))
            c, d = sorted(rng.sample(range(100), 2))
            naive = bool(set(range(a, b)) & set(range(c, d)))
            self.assertEqual(overlaps(a, b, c, d), naive)

    def test_clash_names_who(self):
        p = check_booking(at(10), at(11), [(at(9), at(10, 30), "Class 6")])
        self.assertIn("clashes with Class 6", p[0])

    def test_back_to_back_is_fine(self):
        self.assertEqual(check_booking(at(10), at(11), [(at(9), at(10), "x")]), [])

    def test_rules(self):
        self.assertIn("end must be after", check_booking(at(11), at(10), [])[0])
        self.assertIn("open 8:00", check_booking(at(7), at(9), [])[0])
        self.assertIn("open 8:00", check_booking(at(17), at(18, 30), [])[0])
        self.assertEqual(check_booking(at(17), at(18), []), [])
        self.assertIn("passed", check_booking(at(9), at(10), [], now=at(12))[0])
        self.assertIn("one day", check_booking(at(17), at(9, d=4), [])[0])

    def test_free_slots(self):
        s = free_slots(date(2026, 11, 3), [(at(9), at(10), "a"), (at(10), at(12), "b"), (at(16), at(18), "c")])
        self.assertEqual(s, [(at(8), at(9)), (at(12), at(16))])

    def test_free_slots_skip_tiny_gaps(self):
        self.assertEqual(free_slots(date(2026, 11, 3), [(at(8), at(12), "a"), (at(12, 10), at(18), "b")]), [])

    def test_parse(self):
        self.assertEqual(parse_time("2026-11-03T09:30"), at(9, 30))
        with self.assertRaises(ValueError):
            parse_time("soon")


class TestTickets(unittest.TestCase):
    def test_due_times(self):
        self.assertEqual(ticket_due("urgent", T), T + timedelta(hours=4))
        with self.assertRaises(ValueError):
            ticket_due("whenever", T)

    def test_states(self):
        self.assertEqual(ticket_state("urgent", T, None, T + timedelta(hours=3)), "open")
        self.assertEqual(ticket_state("urgent", T, None, T + timedelta(hours=5)), "overdue")
        self.assertEqual(ticket_state("urgent", T, T + timedelta(hours=1), T), "closed in time")
        self.assertEqual(ticket_state("urgent", T, T + timedelta(hours=9), T), "closed late")

    def test_report(self):
        r = sla_report([("urgent", T, T + timedelta(hours=2)), ("urgent", T, T + timedelta(hours=6)), ("low", T, None), ("urgent", T, None)], T + timedelta(hours=10))
        self.assertEqual((r["open"], r["overdue"], r["in_time"], r["mean_hours"]), (2, 1, 0.5, 4))

    def test_empty_report(self):
        self.assertIsNone(sla_report([], T)["in_time"])


class TestUpkeep(unittest.TestCase):
    D = date(2026, 11, 3)

    def test_never_serviced_is_due_now(self):
        self.assertEqual(next_due(None, 90, self.D), self.D)

    def test_list(self):
        rows = maintenance_list([("a", date(2026, 6, 1), 90), ("b", date(2026, 10, 30), 180), ("c", date(2026, 8, 20), 80)], self.D)
        self.assertEqual([r[0] for r in rows], ["a", "c"])
        self.assertEqual(rows[0][2], (self.D - date(2026, 8, 30)).days)

    def test_licences(self):
        self.assertEqual(licence_state(date(2027, 12, 1), 10, 5, self.D), ["ok"])
        self.assertEqual(licence_state(date(2026, 1, 1), 10, 5, self.D), ["expired"])
        self.assertEqual(licence_state(date(2026, 11, 13), 10, 12, self.D), ["expires in 10 days", "2 seats over the limit"])
        self.assertEqual(licence_state(None, 1, 1, self.D), ["ok"])

    def test_rates(self):
        self.assertEqual(fault_rate(5, 1000), 0.5)
        self.assertEqual(fault_rate(5, 0), 0)
        rows = worst_devices({"old": 4, "new": 2}, {"old": 3650, "new": 60})
        self.assertEqual(rows[0][0], "new")


class TestApp(unittest.TestCase):
    def setUp(self):
        self.a = create_app(":memory:", lambda: datetime(2026, 11, 3, 9))

    def text(self, url):
        return self.a.get(url).body.decode()

    def test_devices(self):
        self.assertEqual(self.a.post("/devices", tag="PC-01", kind="Desktop", every_days=90).status, 303)
        self.assertEqual(self.a.post("/devices", tag="PC-01", kind="Desktop").status, 409)
        self.assertIn("PC-01", self.text("/devices"))
        self.assertIn("PC-01", self.text("/"))
        self.a.post("/device/1", action="service")
        self.assertNotIn("PC-01", self.text("/").split("Service due soon")[1])
        self.assertIn("PC-01", self.a.get("/devices.csv").body.decode())

    def test_retired_devices_leave_the_list(self):
        self.a.post("/devices", tag="PC-01", kind="Desktop")
        self.a.post("/device/1", status="retired")
        self.assertNotIn("PC-01", self.text("/"))
        self.assertEqual(self.a.post("/device/1", status="melted").status, 400)

    def test_booking_clash_offers_free_times(self):
        ok = dict(who="Class 6", day="2026-11-03", start="10:00", end="11:00")
        self.assertEqual(self.a.post("/bookings", **ok).status, 303)
        r = self.a.post("/bookings", **{**ok, "who": "Class 7", "start": "10:30", "end": "11:30"})
        self.assertEqual(r.status, 400)
        self.assertIn("clashes with Class 6", r.body.decode())
        self.assertIn("Free times", r.body.decode())

    def test_booking_in_the_past(self):
        self.assertEqual(self.a.post("/bookings", who="x", day="2026-11-03", start="08:00", end="08:30").status, 400)

    def test_fault_flow(self):
        self.a.post("/devices", tag="PC-01", kind="Desktop")
        self.a.post("/tickets", device=1, problem="No display", priority="high")
        self.assertEqual(self.a.one("SELECT status FROM devices"), "faulty")
        self.assertIn("No display", self.text("/tickets"))
        self.assertEqual(self.a.post("/tickets", close=1, fix="New cable").status, 303)
        self.assertEqual(self.a.post("/tickets", close=1, fix="again").status, 409)
        self.assertIn("New cable", self.text("/device/1"))

    def test_licences_page(self):
        self.a.post("/licences", name="Office", seats=10, used=12, expires="2026-12-01")
        self.assertIn("2 seats over", self.text("/licences"))


if __name__ == "__main__":
    unittest.main()
