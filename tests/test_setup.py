import os
import tempfile

from tesla_charge_oracle.config import load_settings
from tesla_charge_oracle.setup import run_setup


def test_setup_scripted_answers_write_loadable_config():
    # Answers in wizard order: car, VIN, pack, kW, target, current,
    # deadline, peak start, peak end, offpeak end, 3 rates,
    # AI choice (2 = never), model name.
    answers = iter(["Model 3", "", "75", "11.5", "85", "35", "6:30 AM",
                    "4:00 PM", "9:00 PM", "8:00 AM", "0.55", "0.35", "0.25",
                    "2", "llama3.1"])
    printed = []
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".env")
        run_setup(input_fn=lambda prompt: next(answers),
                  print_fn=printed.append, env_path=path)
        with open(path, encoding="utf-8") as fh:
            env = {}
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key] = val
    settings = load_settings(env)
    assert settings.vehicles[0].name == "Model 3"
    assert settings.target_soc == 85
    assert settings.current_soc == 35
    assert settings.deadline == "6:30 AM"
    assert settings.rate_peak == 0.55
    assert settings.ai_mode == "never"


def test_setup_defaults_on_empty_answers():
    answers = iter(["", "", "", "", "", "", "", "", "", "", "", "", "",
                    "1", ""])
    # First choice prompt is AI mode; "1" = auto, then AI URL prompt
    # consumes the next "" (default URL) — feed one extra for the model.
    answers = iter(["", "", "", "", "", "", "", "", "", "", "", "", "",
                    "1", "", "llama3.1"])
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, ".env")
        run_setup(input_fn=lambda prompt: next(answers),
                  print_fn=lambda *a: None, env_path=path)
        with open(path, encoding="utf-8") as fh:
            env = {}
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env[key] = val
    settings = load_settings(env)
    assert settings.vehicles[0].name == "Model Y"
    assert settings.target_soc == 90
    assert settings.deadline == "7:00 AM"
