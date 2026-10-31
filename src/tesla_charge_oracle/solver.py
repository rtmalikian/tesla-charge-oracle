"""Deterministic charge-window solver. No network, `now` injected.

Given: current SoC, target SoC, usable pack size, charger power, and a
three-band time-of-use rate table, the solver picks the cheapest
15-minute slots between now and the deadline that deliver the needed
energy, then merges consecutive slots into charge windows.

Invariants the tests pin down:
  - never charges past the target (last slot is trimmed, never overshoots);
  - if there is not enough time, it charges as much as possible and
    reports the shortfall honestly instead of promising the target;
  - if the car is already at/above target, the plan is empty, cost $0;
  - the cheapest plan never costs more than charging continuously now.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .config import format_time_12h, parse_time_12h

SLOT_MINUTES = 15


def _in_window(minutes: int, start: int, end: int) -> bool:
    """Half-open [start, end); wraps past midnight when end <= start."""
    if start == end:
        return False
    if start < end:
        return start <= minutes < end
    return minutes >= start or minutes < end


@dataclass
class RateTable:
    peak_start: int
    peak_end: int
    offpeak_end: int
    rate_peak: float
    rate_mid: float
    rate_offpeak: float

    @classmethod
    def from_settings(cls, s) -> "RateTable":
        return cls(parse_time_12h(s.peak_start), parse_time_12h(s.peak_end),
                   parse_time_12h(s.offpeak_end), s.rate_peak, s.rate_mid,
                   s.rate_offpeak)

    def band(self, when: datetime) -> str:
        mins = when.hour * 60 + when.minute
        if _in_window(mins, self.peak_start, self.peak_end):
            return "peak"
        # Off-peak runs from peak end overnight until offpeak_end.
        if _in_window(mins, self.peak_end, self.offpeak_end):
            return "off-peak"
        return "mid-peak"

    def rate(self, when: datetime) -> float:
        return {"peak": self.rate_peak, "mid-peak": self.rate_mid,
                "off-peak": self.rate_offpeak}[self.band(when)]


@dataclass
class Window:
    start: datetime
    end: datetime
    band: str
    rate: float
    battery_kwh: float
    wall_kwh: float
    cost: float

    def describe(self) -> str:
        fmt = "%I:%M %p"
        return (f"{self.start.strftime(fmt)}–{self.end.strftime(fmt)} "
                f"({self.band}, ${self.rate:.2f}/kWh, "
                f"{self.battery_kwh:.1f} kWh into the battery, "
                f"${self.cost:.2f})")


@dataclass
class Plan:
    vehicle: str
    current_soc: int
    target_soc: int
    deadline: datetime
    windows: list[Window] = field(default_factory=list)
    reached_soc: float = 0.0
    total_cost: float = 0.0
    total_wall_kwh: float = 0.0
    shortfall_kwh: float = 0.0
    continuous_cost: float = 0.0

    @property
    def achieved(self) -> bool:
        return self.shortfall_kwh <= 1e-9 and self.reached_soc >= self.target_soc - 1e-9

    @property
    def savings(self) -> float:
        return round(self.continuous_cost - self.total_cost, 2)

    def summary(self) -> str:
        if self.current_soc >= self.target_soc:
            return (f"Your {self.vehicle} is already at {self.current_soc}% — "
                    f"at or above your {self.target_soc}% target, so no "
                    f"charging is needed. Cost: $0.00.")
        if not self.windows:
            return (f"No charge time is available before "
                    f"{self.deadline.strftime('%I:%M %p')}. Plug in and "
                    f"charge as soon as you can — the car is at "
                    f"{self.current_soc}% and needs {self.target_soc}%.")
        lines = [f"Cheapest way to {self.target_soc}% by "
                 f"{self.deadline.strftime('%I:%M %p')} for your {self.vehicle}:"]
        for w in self.windows:
            lines.append(f"  • Charge {w.describe()}")
        lines.append(f"Total: ${self.total_cost:.2f} for "
                     f"{self.total_wall_kwh:.1f} kWh from the wall "
                     f"({sum(w.battery_kwh for w in self.windows):.1f} kWh "
                     f"into the battery).")
        if self.achieved:
            lines.append(f"You'll reach {self.target_soc}% by the deadline.")
        else:
            lines.append(f"Warning: even charging the whole time only reaches "
                         f"{self.reached_soc:.0f}% — {self.shortfall_kwh:.1f} kWh "
                         f"short of {self.target_soc}%. Leave earlier, plug "
                         f"in sooner, or lower the target.")
        if self.savings > 0:
            lines.append(f"That's ${self.savings:.2f} cheaper than charging "
                         f"straight away from now.")
        return "\n".join(lines)


def solve(vehicle: str, current_soc: int, target_soc: int, battery_kwh: float,
          charge_kw: float, efficiency: float, rates: RateTable,
          now: datetime, deadline: datetime) -> Plan:
    needed_battery = max(0.0, (target_soc - current_soc) / 100.0 * battery_kwh)
    plan = Plan(vehicle=vehicle, current_soc=current_soc,
                target_soc=target_soc, deadline=deadline,
                reached_soc=float(current_soc))
    if needed_battery <= 0 or deadline <= now:
        return plan
    # Build 15-minute slots from now (rounded up) to the deadline.
    slot_start = now.replace(second=0, microsecond=0)
    remainder = slot_start.minute % SLOT_MINUTES
    if remainder:
        slot_start += timedelta(minutes=SLOT_MINUTES - remainder)
    slots = []
    t = slot_start
    while t < deadline:
        slots.append(t)
        t += timedelta(minutes=SLOT_MINUTES)
    if not slots:
        return plan
    per_slot_battery = charge_kw * (SLOT_MINUTES / 60.0) * efficiency
    per_slot_wall = charge_kw * (SLOT_MINUTES / 60.0)
    # Cheapest first; ties break toward earlier slots (start sooner).
    ranked = sorted(slots, key=lambda s: (rates.rate(s), s))
    remaining = needed_battery
    chosen: dict[datetime, float] = {}
    for slot in ranked:
        if remaining <= 0:
            break
        take = min(per_slot_battery, remaining)
        chosen[slot] = take
        remaining -= take
    plan.shortfall_kwh = round(remaining, 4)
    # Continuous-from-now cost, for the savings comparison.
    cont_remaining, cont_cost = needed_battery, 0.0
    for slot in slots:
        if cont_remaining <= 0:
            break
        take = min(per_slot_battery, cont_remaining)
        cont_cost += (take / efficiency) * rates.rate(slot)
        cont_remaining -= take
    plan.continuous_cost = round(cont_cost, 2)
    # Merge consecutive chosen slots (same band) into windows.
    for slot in sorted(chosen):
        take = chosen[slot]
        wall = take / efficiency
        cost = wall * rates.rate(slot)
        if (plan.windows and plan.windows[-1].end == slot
                and plan.windows[-1].band == rates.band(slot)):
            w = plan.windows[-1]
            w.end = slot + timedelta(minutes=SLOT_MINUTES)
            w.battery_kwh += take
            w.wall_kwh += wall
            w.cost += cost
        else:
            plan.windows.append(Window(
                start=slot, end=slot + timedelta(minutes=SLOT_MINUTES),
                band=rates.band(slot), rate=rates.rate(slot),
                battery_kwh=take, wall_kwh=wall, cost=cost))
    plan.total_cost = round(sum(w.cost for w in plan.windows), 2)
    plan.total_wall_kwh = round(sum(w.wall_kwh for w in plan.windows), 2)
    delivered = sum(w.battery_kwh for w in plan.windows)
    plan.reached_soc = round(
        current_soc + delivered / battery_kwh * 100.0, 1) if battery_kwh else float(current_soc)
    return plan


def next_deadline(deadline_text: str, now: datetime) -> datetime:
    """Today at the named time, or tomorrow if that time already passed."""
    mins = parse_time_12h(deadline_text)
    candidate = now.replace(hour=mins // 60, minute=mins % 60,
                            second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate
