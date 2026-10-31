"""Configuration for Tesla Charge Oracle. All settings come from the
environment (see .env.example). Run `tcoracle setup` and answer a few
plain-language questions — it writes .env for you. .env is git-ignored
so secrets never leave your machine.

Time-of-use model, in plain words: the day is split into three price
bands. Peak = your expensive evening window (default 4:00 PM–9:00 PM).
Off-peak = overnight, from the end of peak until the morning hour you
pick (default 8:00 AM). Mid-peak = everything else (daytime).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


class ConfigError(Exception):
    pass


@dataclass
class VehicleConfig:
    name: str
    vin: str = ""


@dataclass
class Settings:
    client_id: str = ""
    client_secret: str = ""
    region: str = "na"
    redirect_uri: str = "http://localhost:8080/callback"
    token_file: str = "~/.tco/tokens.json"
    vehicles: list[VehicleConfig] = field(default_factory=list)
    server_host: str = "127.0.0.1"
    server_port: int = 8646
    server_api_key: str = ""
    model_id: str = "tesla-charge-oracle"
    ai_base_url: str = "http://localhost:11434/v1"
    ai_api_key: str = ""
    ai_model: str = "llama3.1"
    ai_mode: str = "auto"
    ai_timeout_seconds: float = 20.0
    embedding_dim: int = 384
    dry_run: bool = False
    data_dir: str = "~/.tco"
    # ---- Charge Oracle settings --------------------------------------
    target_soc: int = 90
    current_soc: int = 40
    battery_kwh: float = 75.0
    charge_kw: float = 11.5
    efficiency: float = 0.90
    deadline: str = "7:00 AM"
    peak_start: str = "4:00 PM"
    peak_end: str = "9:00 PM"
    offpeak_end: str = "8:00 AM"
    rate_peak: float = 0.55
    rate_mid: float = 0.35
    rate_offpeak: float = 0.25


def _parse_vehicles(raw: str) -> list[VehicleConfig]:
    vehicles = []
    for idx, item in enumerate(raw.split(",")):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            name, vin = item.split("=", 1)
            vehicles.append(VehicleConfig(name=name.strip() or f"car-{idx + 1}",
                                          vin=vin.strip()))
        else:
            vehicles.append(VehicleConfig(name=item, vin=""))
    if not vehicles:
        raise ConfigError("TCO_VEHICLES is empty — add at least one car nickname")
    return vehicles


def _int(env, key, default):
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{key} must be a whole number, got {raw!r}") from exc


def _float(env, key, default):
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


def _bool(env, key, default=False):
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


_TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([aApP][mM])?\s*$")


def parse_time_12h(text: str) -> int:
    """'7:00 AM' / '7am' / '19:00' -> minutes since midnight. Raises ValueError."""
    m = _TIME_RE.match(str(text))
    if not m:
        raise ValueError(f"Can't read the time {text!r} — use a time like '7:00 AM'.")
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if minute > 59:
        raise ValueError(f"Minutes must be 0–59, got {minute} in {text!r}.")
    if ampm:
        if not (1 <= hour <= 12):
            raise ValueError(f"Hour must be 1–12 with AM/PM, got {hour}.")
        if ampm.lower() == "pm" and hour != 12:
            hour += 12
        if ampm.lower() == "am" and hour == 12:
            hour = 0
    else:
        if not (0 <= hour <= 23):
            raise ValueError(f"Hour must be 0–23, got {hour}.")
    return hour * 60 + minute


def format_time_12h(minutes: int) -> str:
    minutes %= 24 * 60
    h, m = divmod(minutes, 60)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def load_settings(env: dict | None = None) -> Settings:
    env = os.environ if env is None else env
    s = Settings()
    s.client_id = env.get("TESLA_CLIENT_ID", "")
    s.client_secret = env.get("TESLA_CLIENT_SECRET", "")
    s.region = env.get("TESLA_REGION", "na").strip().lower()
    if s.region not in ("na", "eu", "cn"):
        raise ConfigError(f"TESLA_REGION must be na|eu|cn, got {s.region!r}")
    s.redirect_uri = env.get("TESLA_REDIRECT_URI", s.redirect_uri)
    s.token_file = env.get("TCO_TOKEN_FILE", s.token_file)
    raw_vehicles = env.get("TCO_VEHICLES", "")
    if raw_vehicles.strip():
        s.vehicles = _parse_vehicles(raw_vehicles)
    s.server_host = env.get("TCO_SERVER_HOST", s.server_host)
    s.server_port = _int(env, "TCO_SERVER_PORT", s.server_port)
    s.server_api_key = env.get("TCO_SERVER_API_KEY", "")
    s.model_id = env.get("TCO_MODEL_ID", s.model_id)
    s.ai_base_url = env.get("TCO_AI_BASE_URL", s.ai_base_url).rstrip("/")
    s.ai_api_key = env.get("TCO_AI_API_KEY", "")
    s.ai_model = env.get("TCO_AI_MODEL", s.ai_model)
    s.ai_mode = env.get("TCO_AI_MODE", s.ai_mode).strip().lower()
    if s.ai_mode not in ("auto", "always", "never"):
        raise ConfigError(f"TCO_AI_MODE must be auto|always|never, got {s.ai_mode!r}")
    s.ai_timeout_seconds = _float(env, "TCO_AI_TIMEOUT_SECONDS", s.ai_timeout_seconds)
    s.embedding_dim = _int(env, "TCO_EMBEDDING_DIM", s.embedding_dim)
    if not (8 <= s.embedding_dim <= 4096):
        raise ConfigError("TCO_EMBEDDING_DIM must be between 8 and 4096")
    s.dry_run = _bool(env, "TCO_DRY_RUN")
    s.data_dir = env.get("TCO_DATA_DIR", s.data_dir)
    s.target_soc = _int(env, "TCO_TARGET_SOC", s.target_soc)
    if not (50 <= s.target_soc <= 100):
        raise ConfigError(f"TCO_TARGET_SOC must be 50 to 100, got {s.target_soc}")
    s.current_soc = _int(env, "TCO_CURRENT_SOC", s.current_soc)
    if not (0 <= s.current_soc <= 100):
        raise ConfigError(f"TCO_CURRENT_SOC must be 0 to 100, got {s.current_soc}")
    s.battery_kwh = _float(env, "TCO_BATTERY_KWH", s.battery_kwh)
    if not (30 <= s.battery_kwh <= 200):
        raise ConfigError(f"TCO_BATTERY_KWH must be 30 to 200, got {s.battery_kwh}")
    s.charge_kw = _float(env, "TCO_CHARGE_KW", s.charge_kw)
    if not (1 <= s.charge_kw <= 22):
        raise ConfigError(f"TCO_CHARGE_KW must be 1 to 22, got {s.charge_kw}")
    s.efficiency = _float(env, "TCO_EFFICIENCY", s.efficiency)
    if not (0.5 <= s.efficiency <= 1.0):
        raise ConfigError(f"TCO_EFFICIENCY must be 0.5 to 1.0, got {s.efficiency}")
    s.deadline = env.get("TCO_DEADLINE", s.deadline).strip()
    s.peak_start = env.get("TCO_PEAK_START", s.peak_start).strip()
    s.peak_end = env.get("TCO_PEAK_END", s.peak_end).strip()
    s.offpeak_end = env.get("TCO_OFFPEAK_END", s.offpeak_end).strip()
    for label, val in (("TCO_DEADLINE", s.deadline), ("TCO_PEAK_START", s.peak_start),
                       ("TCO_PEAK_END", s.peak_end), ("TCO_OFFPEAK_END", s.offpeak_end)):
        try:
            parse_time_12h(val)
        except ValueError as exc:
            raise ConfigError(f"{label}: {exc}") from exc
    s.rate_peak = _float(env, "TCO_RATE_PEAK", s.rate_peak)
    s.rate_mid = _float(env, "TCO_RATE_MID", s.rate_mid)
    s.rate_offpeak = _float(env, "TCO_RATE_OFFPEAK", s.rate_offpeak)
    for label, val in (("TCO_RATE_PEAK", s.rate_peak), ("TCO_RATE_MID", s.rate_mid),
                       ("TCO_RATE_OFFPEAK", s.rate_offpeak)):
        if not (0 <= val <= 5):
            raise ConfigError(f"{label} must be 0 to 5 dollars per kWh, got {val}")
    return s
