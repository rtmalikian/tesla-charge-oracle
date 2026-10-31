# Tesla Charge Oracle — Cheapest Way to Charge Your Tesla by Morning (Model 3, Model Y, Model S, Model X, Cybertruck)

**Free, open-source Tesla Fleet API app: ask "cheapest way to 90% by 7am?" and get the exact cheapest charge windows, total cost, and savings versus charging straight away — from your real time-of-use electricity rates.**

▶ **[Try the live demo](https://rtmalikian.github.io/tesla-charge-oracle/)** — drag the sliders, set your rates, and watch the solver pick the cheapest overnight windows. Pretend data only, no install, no car needed.

## Why?

Electricity is not one price any more. On a California time-of-use plan the same kilowatt-hour can cost $0.25 overnight or $0.55 at 6 PM — and a full charge is 40+ kWh, so charging at the wrong hour quietly costs $10+ extra per charge. Tesla lets you *schedule* charging, but it doesn't *optimize* it: no tool looks at your rates, your target, and your deadline and says "charge 9 PM–12:45 AM, skip the expensive hours, save $10." Charge Oracle does exactly that, in plain language, and answers it through a standard AI chat endpoint so any OpenAI-compatible client can ask.

**No AI needed:** the solver computes every plan from your rates with zero AI involved. The optional AI layer only explains plans in free-form chat — the rules engine always decides.

## How it works

Ask in plain words; the solver picks the cheapest 15-minute slots between now and your deadline, merges them into windows, and prices them:

```
You plug in at 6:00 PM at 40%, target 90% by 7:00 AM, 11.5 kW charger
  6:00 PM–9:00 PM   Peak ($0.55/kWh) — SKIPPED, too expensive
  9:00 PM–12:45 AM  Off-peak ($0.25/kWh) — CHARGE (37.5 kWh into the battery)
  Total: $10.42 — $10.35 cheaper than charging straight away from 6 PM
  (If even charging the whole night can't reach the target, it says so
   honestly — with the shortfall — instead of promising 90%.)
```

## Quickstart (owners, not developers)

```bash
git clone https://github.com/rtmalikian/tesla-charge-oracle.git
cd tesla-charge-oracle
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
tcoracle setup      # plain-language questions; writes .env for you
tcoracle simulate   # see the cheapest plan on pretend data
tcoracle preview --target 90 --current 40 --by "7:00 AM"  # dry run, changes nothing
tcoracle plan       # your own cheapest plan, plain English
tcoracle serve      # start the OpenAI-compatible chat server
```

What you'll see when it works: `simulate` prints three scenarios — the headline overnight plan, an already-at-target car costing $0, and a too-short night with an honest shortfall — ending in a $0.00 API cost line. `preview` prints one plain-English plan and says what *would* happen — it sends nothing to any car.

## Tesla developer setup

Live execution uses the standard Fleet API flow: create an app at developer.tesla.com, authorize once, pair a virtual key (`tcoracle` will print the pairing link). Until a car is paired, `plan`, `preview`, and `apply` work on your settings and the solver — `apply` records the plan and asks for confirmation first, and never claims a send it didn't make.

## `.env` reference

| Variable | Default | What it means |
|---|---|---|
| `TCO_VEHICLES` | — | Your cars, `nickname=VIN` pairs (VIN optional) |
| `TCO_TARGET_SOC` / `TCO_CURRENT_SOC` | 90 / 40 | Target and current battery percent |
| `TCO_BATTERY_KWH` / `TCO_CHARGE_KW` | 75 / 11.5 | Usable pack size, home charger speed |
| `TCO_DEADLINE` | 7:00 AM | When the car must be ready (12-hour words) |
| `TCO_PEAK_START` / `TCO_PEAK_END` | 4:00 PM / 9:00 PM | Your expensive evening window |
| `TCO_OFFPEAK_END` | 8:00 AM | Overnight cheap rate runs until this morning time |
| `TCO_RATE_PEAK` / `TCO_RATE_MID` / `TCO_RATE_OFFPEAK` | 0.55 / 0.35 / 0.25 | Dollars per kWh per band |
| `TCO_AI_BASE_URL` / `TCO_AI_MODEL` / `TCO_AI_MODE` | Ollama / llama3.1 / auto | Pluggable LLM backend; `never` = built-in answers only |
| `TCO_SERVER_HOST` / `TCO_SERVER_PORT` | 127.0.0.1 / 8646 | The chat server's address |
| `TCO_SERVER_API_KEY` | — | Optional bearer token for the server |
| `TCO_DRY_RUN` | 0 | 1 = plan and explain, never apply anything |

## AI endpoints

Charge Oracle exposes an OpenAI-compatible surface (stdlib HTTP server, no framework). Vehicle data goes **only** to your configured LLM backend, nowhere else.

```bash
# What models are available?
curl http://127.0.0.1:8646/v1/models

# The cheapest way to 90% by 7am, in plain language:
curl http://127.0.0.1:8646/v1/chat/completions -d '{
  "model": "tesla-charge-oracle",
  "messages": [{"role": "user",
    "content": "cheapest way to 90% by 7am, currently at 40%"}]}'

# Embeddings over charge-plan text (local deterministic hashing, dim 384):
curl http://127.0.0.1:8646/v1/embeddings -d '{
  "input": "cheap overnight charging to 90 percent"}'
```

LLM-emitted commands are validated against a strict allowlist (`plan_charge`, `set_charge_limit`, `start_charging`, `stop_charging`) before anything runs. Dry-run is honored everywhere.

## Expected API cost

**~$0.10–0.30/month at a daily plan.** One data read per plan plus one command per window actually applied; wakes dominate the Fleet API bill, and this app never wakes a car to measure anything. The simulator itself costs $0.00 — it makes no live calls.

## FAQ

**Does this change when my car charges, or just tell me?**
It tells you first (`plan`/`preview` always come before `apply`), and `apply` records the plan for execution once a car is paired — with a confirmation prompt. Nothing is ever sent silently.

**What if I plug in during peak hours?**
The solver skips peak slots whenever cheaper ones can still hit the target — that's where the savings come from. If only peak slots can reach the target in time, it uses them and says so plainly.

**What if there's not enough time to reach my target?**
It charges as much as possible in the time available and reports the shortfall honestly ("reaches 44%, 34.6 kWh short of 90%") instead of promising a target it can't hit.

**Do I need an AI backend or a paid API key?**
No. The solver, the planner, and the simulator all work with the AI backend off (`TCO_AI_MODE=never`). The AI layer only powers free-form explanations.

**My utility's rates don't match the defaults — what then?**
Run `tcoracle setup` and type your own peak window and three rates in plain words, or edit the `TCO_RATE_*` lines. The solver adapts to any three-band plan, including peak windows that cross midnight.

**Does it send my driving or charging data anywhere?**
No. Plans live on your machine; vehicle data goes only to the LLM backend you configure (local Ollama by default), nowhere else.

## License

MIT — Raphael Malikian.
