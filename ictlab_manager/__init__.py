"""ICT Lab Manager: devices, bookings, faults, maintenance and licences."""
from . import core
from .web import create_app

__all__ = ["core", "create_app"]
