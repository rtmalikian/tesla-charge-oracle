from datetime import datetime

from tesla_charge_oracle.solver import RateTable, next_deadline, solve

RATES = RateTable(peak_start=16 * 60, peak_end=21 * 60, offpeak_end=8 * 60,
                  rate_peak=0.55, rate_mid=0.35, rate_offpeak=0.25)


def _solve(now, deadline, current=40, target=90, kw=11.5, pack=75.0):
    return solve("Model Y", current, target, pack, kw, 0.90, RATES, now, deadline)


def test_cheapest_plan_beats_continuous_and_hits_target():
    plan = _solve(datetime(2026, 10, 31, 18, 0), datetime(2026, 11, 1, 7, 0))
    assert plan.achieved
    assert plan.reached_soc >= 90
    assert plan.total_cost <= plan.continuous_cost
    assert plan.savings > 0
    # No peak window should be chosen while off-peak slots are available.
    assert all(w.band != "peak" for w in plan.windows)
    # Windows are chronological and non-overlapping.
    for a, b in zip(plan.windows, plan.windows[1:]):
        assert a.end <= b.start


def test_already_at_target_costs_nothing():
    plan = _solve(datetime(2026, 10, 31, 18, 0), datetime(2026, 11, 1, 7, 0),
                  current=95, target=90)
    assert plan.windows == [] and plan.total_cost == 0.0


def test_shortfall_reported_honestly():
    plan = _solve(datetime(2026, 10, 31, 6, 0), datetime(2026, 11, 1, 7, 0)
                  if False else datetime(2026, 10, 31, 7, 0),
                  current=30, target=90)
    assert not plan.achieved
    assert plan.shortfall_kwh > 0
    assert plan.reached_soc < 90
    assert "short" in plan.summary().lower()


def test_no_time_available():
    plan = _solve(datetime(2026, 10, 31, 18, 0), datetime(2026, 10, 31, 18, 0))
    assert plan.windows == []


def test_peak_only_evening_priced_honestly():
    # Plug in at 4:30 PM, deadline 6 PM: only peak slots exist.
    plan = _solve(datetime(2026, 10, 31, 16, 30), datetime(2026, 10, 31, 18, 0),
                  current=40, target=60)
    assert plan.windows and all(w.band == "peak" for w in plan.windows)
    assert plan.total_cost == plan.continuous_cost  # no cheaper alternative


def test_last_slot_trimmed_no_overshoot():
    plan = _solve(datetime(2026, 10, 31, 18, 0), datetime(2026, 11, 1, 7, 0),
                  current=89, target=90, kw=11.5, pack=75.0)
    assert plan.reached_soc <= 90.1
    assert plan.achieved


def test_rate_bands():
    assert RATES.band(datetime(2026, 10, 31, 17, 0)) == "peak"
    assert RATES.band(datetime(2026, 10, 31, 23, 0)) == "off-peak"
    assert RATES.band(datetime(2026, 10, 31, 2, 0)) == "off-peak"
    assert RATES.band(datetime(2026, 10, 31, 10, 0)) == "mid-peak"
    assert RATES.band(datetime(2026, 10, 31, 21, 0)) == "off-peak"
    assert RATES.band(datetime(2026, 10, 31, 16, 0)) == "peak"


def test_next_deadline_rolls_to_tomorrow():
    now = datetime(2026, 10, 31, 18, 0)
    assert next_deadline("7:00 AM", now) == datetime(2026, 11, 1, 7, 0)
    assert next_deadline("9:00 PM", now) == datetime(2026, 10, 31, 21, 0)
