import pytest

from tesla_charge_oracle.config import (
    ConfigError, format_time_12h, load_settings, parse_time_12h)


def test_time_parsing():
    assert parse_time_12h("7:00 AM") == 420
    assert parse_time_12h("7am") == 420
    assert parse_time_12h("12:00 AM") == 0
    assert parse_time_12h("12:00 PM") == 720
    assert parse_time_12h("9:00 PM") == 1260
    assert parse_time_12h("19:00") == 1140
    assert format_time_12h(420) == "7:00 AM"
    assert format_time_12h(0) == "12:00 AM"
    with pytest.raises(ValueError):
        parse_time_12h("25:00 AM")
    with pytest.raises(ValueError):
        parse_time_12h("7:99 AM")


def test_defaults_and_overrides():
    s = load_settings({})
    assert s.target_soc == 90 and s.rate_offpeak == 0.25
    assert s.server_port == 8646 and s.ai_mode == "auto"
    s = load_settings({"TCO_VEHICLES": "Model Y=VIN1,Model 3",
                       "TCO_TARGET_SOC": "80", "TCO_RATE_PEAK": "0.60"})
    assert [v.name for v in s.vehicles] == ["Model Y", "Model 3"]
    assert s.vehicles[1].vin == ""
    assert s.target_soc == 80 and s.rate_peak == 0.60


def test_invalid_values_rejected():
    with pytest.raises(ConfigError):
        load_settings({"TCO_TARGET_SOC": "40"})
    with pytest.raises(ConfigError):
        load_settings({"TCO_TARGET_SOC": "abc"})
    with pytest.raises(ConfigError):
        load_settings({"TCO_AI_MODE": "sometimes"})
    with pytest.raises(ConfigError):
        load_settings({"TCO_DEADLINE": "tomorrow morning"})
    with pytest.raises(ConfigError):
        load_settings({"TESLA_REGION": "xx"})
    with pytest.raises(ConfigError):
        load_settings({"TCO_RATE_PEAK": "-1"})
    with pytest.raises(ConfigError):
        load_settings({"TCO_VEHICLES": ",,,"})
