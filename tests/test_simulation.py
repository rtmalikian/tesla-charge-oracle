from tesla_charge_oracle.config import Settings, VehicleConfig
from tesla_charge_oracle.simulator import render_demo, run_demo


def test_simulation_invariants():
    settings = Settings(vehicles=[VehicleConfig("Model Y", "VINY")],
                        ai_mode="never")
    scenarios = run_demo(settings)
    assert len(scenarios) == 3
    headline, already, short = [p for _, p in scenarios]
    assert headline.achieved
    assert headline.total_cost <= headline.continuous_cost
    assert already.windows == [] and already.total_cost == 0.0
    assert not short.achieved and short.shortfall_kwh > 0
    text = render_demo(scenarios)
    assert "Cheapest way" in text and "$0.00" in text
