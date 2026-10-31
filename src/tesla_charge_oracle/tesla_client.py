"""Minimal Fleet API client surface for Charge Oracle.

The charge commands this app plans around — set_charge_limit,
start/stop charging — are real Fleet API commands. Live sends need a
paired car (developer.tesla.com app + virtual key); until pairing is
done, this module refuses to pretend a send happened and points at the
planner/simulator instead. When paired, these methods are where the
signed Fleet API calls live.
"""
from __future__ import annotations


class NotPairedError(Exception):
    """Raised when code asks a real car to act before pairing."""


class TeslaClient:
    def __init__(self, *args, **kwargs):
        pass

    def authorize_url(self) -> str:
        return ("https://developer.tesla.com/docs/fleet-api "
                "(create an app, authorize once, pair a virtual key)")

    def _not_paired(self, action: str):
        raise NotPairedError(
            f"Can't {action} a real car yet — no paired vehicle. Run "
            f"`tcoracle setup` to fill in your Tesla developer details, "
            f"pair the virtual key, then `tcoracle apply`. Until then, "
            f"`tcoracle plan` and `tcoracle simulate` show the exact "
            f"cheapest plan on pretend data.")

    def set_charge_limit(self, vin: str, percent: int):
        self._not_paired(f"set the charge limit to {percent}%")

    def start_charging(self, vin: str):
        self._not_paired("start charging")

    def stop_charging(self, vin: str):
        self._not_paired("stop charging")
