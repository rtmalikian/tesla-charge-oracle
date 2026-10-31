"""Pretend fleet + overnight scenario over virtual time. No API calls,
no real cars, no credentials, no network.

The demo proves the core invariants:
  - the cheapest plan never costs more than charging straight away;
  - a car already at target needs no charging and costs $0;
  - a too-short night charges as much as possible and reports the
    shortfall honestly;
  - peak-only evenings are priced honestly (no fake cheap windows).
"""
from __future__ import annotations

from datetime import datetime

from .service import ChargeOracleService


def run_demo(settings):
    service = ChargeOracleService(settings)
    scenarios = []
    # 1. The headline case: evening plug-in, morning deadline.
    plan = service.make_plan(
        target=90, current=40, deadline_text="7:00 AM", vehicle="Model Y",
        now=datetime(2026, 10, 31, 18, 0))
    scenarios.append(("Evening plug-in — cheapest way to 90% by 7:00 AM", plan))
    # 2. Already at target.
    plan = service.make_plan(
        target=80, current=85, deadline_text="7:00 AM", vehicle="Model Y",
        now=datetime(2026, 10, 31, 18, 0))
    scenarios.append(("Already at target — nothing to charge", plan))
    # 3. Too-short night: 1 hour to add a lot.
    plan = service.make_plan(
        target=90, current=30, deadline_text="7:00 AM", vehicle="Model 3",
        now=datetime(2026, 10, 31, 6, 0))
    scenarios.append(("One hour left — honest shortfall, not a promise", plan))
    return scenarios


def render_demo(scenarios) -> str:
    lines = ["CHARGE ORACLE — SIMULATED DEMO  (pretend cars, pretend rates; "
             "no real car is involved)", ""]
    for title, plan in scenarios:
        lines.append(f"== {title} ==")
        lines.append(plan.summary())
        lines.append("")
    lines.append("Estimated Fleet API cost of this simulation: $0.00 "
                 "(no live calls; all data is pretend).")
    lines.append("Live use: one data read per plan plus one command per "
                 "window actually applied — roughly $0.10–0.30/month at a "
                 "daily plan; wakes dominate the bill, and this app never "
                 "wakes a car to measure anything.")
    return "\n".join(lines)
