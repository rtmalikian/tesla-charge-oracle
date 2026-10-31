"""Guided first-run setup: plain-language questions, writes .env itself.

Built for Tesla owners, not developers — defaults everywhere, numbered
choices, times in plain words ("7:00 AM"), cars picked by nickname (a
VIN is optional and explained in owner words). Rates are prefilled with
typical Southern California TOU values; change any number in plain words.
No hand-edited config syntax: re-run `tcoracle setup` any time.

`run_setup` takes injectable input/print functions so tests can feed
scripted answers and assert the written config loads.
"""
from __future__ import annotations

import os


def _ask(prompt: str, default: str, ask, out) -> str:
    shown = f"{prompt} [{default}]: " if default else f"{prompt}: "
    answer = ask(shown).strip()
    return answer or default


def _choice(prompt: str, options: list[tuple[str, str]], ask, out) -> str:
    out(prompt)
    for i, (_key, label) in enumerate(options, 1):
        out(f"  {i}) {label}")
    while True:
        raw = ask(f"Pick a number (1-{len(options)}) [1]: ").strip() or "1"
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        out("That's not one of the numbers above — try again.")


def _int_choice(prompt: str, default: int, ask, out) -> int:
    while True:
        raw = _ask(prompt, str(default), ask, out)
        if raw.isdigit():
            return int(raw)
        out("Please type a whole number.")


def _money_choice(prompt: str, default: str, ask, out) -> str:
    while True:
        raw = _ask(prompt, default, ask, out).replace("$", "").strip()
        try:
            float(raw)
            return raw
        except ValueError:
            out("Please type a price like 0.25 (dollars per kWh).")


def run_setup(input_fn=input, print_fn=print, env_path: str = ".env") -> str:
    ask, out = input_fn, print_fn
    out("")
    out("Charge Oracle setup — I'll ask a few plain questions and write")
    out("your settings file for you. Press Enter to accept anything in")
    out("[brackets]. You can re-run this any time to change an answer.")
    out("")
    car = _ask("What do you call your car? (e.g. Model Y, Blue)",
               "Model Y", ask, out)
    vin = _ask("Its VIN, if you know it (in the Tesla app under Controls → "
               "Software; leave blank if not)", "", ask, out)
    out("")
    out("Your car and your usual charge:")
    pack = _ask("How big is your car's battery, in kWh? (Model 3/Y ≈ 75, "
                "Model S/X ≈ 100)", "75", ask, out)
    kw = _ask("How fast does your home charger run, in kW? "
              "(wall connector ≈ 11.5, mobile connector ≈ 7.7)",
              "11.5", ask, out)
    target = _int_choice("What battery level do you usually charge to, "
                         "in percent?", 90, ask, out)
    current = _int_choice("Roughly what level is the car at right now, "
                          "in percent?", 40, ask, out)
    deadline = _ask("By what time do you usually need the car ready? "
                    "(e.g. 7:00 AM)", "7:00 AM", ask, out)
    out("")
    out("Your electricity prices — prefilled with typical California")
    out("time-of-use values; change any of them to match your bill.")
    peak_start = _ask("When does your expensive evening rate start?",
                      "4:00 PM", ask, out)
    peak_end = _ask("When does it end?", "9:00 PM", ask, out)
    offpeak_end = _ask("Overnight cheap rate runs until what morning time?",
                       "8:00 AM", ask, out)
    rate_peak = _money_choice("Expensive rate, dollars per kWh?", "0.55", ask, out)
    rate_mid = _money_choice("Daytime rate, dollars per kWh?", "0.35", ask, out)
    rate_off = _money_choice("Overnight cheap rate, dollars per kWh?",
                             "0.25", ask, out)
    out("")
    ai_mode = _choice("Should the chat server use an AI backend (local "
                      "Ollama by default) to explain plans?", [
        ("auto", "Yes, when one is available (falls back to built-in answers)"),
        ("never", "No — built-in answers only, nothing leaves this computer"),
    ], ask, out)
    ai_url = "http://localhost:11434/v1"
    if ai_mode == "auto":
        ai_url = _ask("Your AI server address (an OpenAI-compatible API)",
                      ai_url, ask, out)
    ai_model = _ask("Which model name should it use?", "llama3.1", ask, out)

    lines = [
        "# Written by `tcoracle setup` — edit by re-running setup any time.",
        "",
        "TESLA_CLIENT_ID=",
        "TESLA_CLIENT_SECRET=",
        "TESLA_REGION=na",
        "TESLA_REDIRECT_URI=http://localhost:8080/callback",
        "",
        f"TCO_VEHICLES={car}={vin}",
        "",
        "TCO_SERVER_HOST=127.0.0.1",
        "TCO_SERVER_PORT=8646",
        "TCO_SERVER_API_KEY=",
        "TCO_MODEL_ID=tesla-charge-oracle",
        "",
        f"TCO_AI_BASE_URL={ai_url}",
        "TCO_AI_API_KEY=",
        f"TCO_AI_MODEL={ai_model}",
        f"TCO_AI_MODE={ai_mode}",
        "TCO_AI_TIMEOUT_SECONDS=20",
        "TCO_EMBEDDING_DIM=384",
        "TCO_TOKEN_FILE=~/.tco/tokens.json",
        "TCO_DATA_DIR=~/.tco",
        "TCO_DRY_RUN=0",
        "",
        f"TCO_TARGET_SOC={target}",
        f"TCO_CURRENT_SOC={current}",
        f"TCO_BATTERY_KWH={pack}",
        f"TCO_CHARGE_KW={kw}",
        "TCO_EFFICIENCY=0.90",
        f"TCO_DEADLINE={deadline}",
        f"TCO_PEAK_START={peak_start}",
        f"TCO_PEAK_END={peak_end}",
        f"TCO_OFFPEAK_END={offpeak_end}",
        f"TCO_RATE_PEAK={rate_peak}",
        f"TCO_RATE_MID={rate_mid}",
        f"TCO_RATE_OFFPEAK={rate_off}",
        "",
    ]
    with open(env_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    out("")
    out(f"Done — settings written to {os.path.abspath(env_path)}.")
    out("Next steps:")
    out("  1) tcoracle simulate  — see the cheapest plan on pretend data")
    out("  2) tcoracle plan      — your own cheapest plan, plain English")
    out("  3) tcoracle serve     — start the AI chat server")
    return os.path.abspath(env_path)
