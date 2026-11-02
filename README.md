# ICT Lab Manager

Everything a computer lab teacher tracks in notebooks and spreadsheets, in one offline app: devices, room bookings, fault reports, servicing and software licences.

```
python -m ictlab_manager
```

Then open http://127.0.0.1:8028. It needs Python 3.10 or newer, and nothing else.

## What it does

- **Device register:** asset tags, status and full fault history, with CSV export
- **Bookings with no clashes:** a clash names who holds the slot and offers free times instead. Back-to-back bookings are allowed
- **Fault tickets:** priorities with response deadlines (urgent 4 hours, high 1 day, normal 3 days, low 1 week), overdue flags, and a share fixed in time
- **Maintenance:** each device has a service interval, and those due in the next two weeks appear on the home page
- **Licences:** seats in use against seats owned, with warnings 60 days before expiry
- **Audit log:** changes to devices are recorded

## How it is tested

Booking overlap logic is compared with a minute-by-minute check on 500 random pairs. Deadlines, service dates and licence rules are tested at their boundaries, and app tests cover clashes, past times, duplicate tags and closing a fault twice. The clock is passed in, so tests control the date.

## Limits

It treats the lab as one bookable room, not individual computers. It is built for one person on one computer, with no logins, so anyone who can reach the app can change data. It does not scan the network for devices.

## Tests

```
python -m unittest discover -s tests
```

MIT licence.
