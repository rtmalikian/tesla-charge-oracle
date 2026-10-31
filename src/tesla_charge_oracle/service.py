"""Transport-independent Charge Oracle service: takes OpenAI-shaped
request dicts, returns OpenAI-shaped response dicts. The HTTP server is
a thin wrapper; tests drive this class directly.

A user message like "cheapest way to 90% by 7am, currently at 40%" is
parsed deterministically and answered from the solver — no AI needed.
Anything else goes to the optional LLM backend with the rates + latest
plan as context; an allowlisted JSON command block is validated before
execution, and dry-run is honored everywhere.

Privacy: plans live on this machine only. Vehicle data goes ONLY to the
user-configured LLM backend, nowhere else.
"""
from __future__ import annotations

import itertools
import re
import time
from datetime import datetime

from .config import parse_time_12h
from .embeddings import embed_text
from .llm import LlmBackend, extract_command
from .solver import RateTable, next_deadline, solve

CAPABILITY_BLURB = (
    "I work out the cheapest way to charge your Tesla to a target level "
    "by a time you pick, using your electricity rates. Ask me, for "
    "example: \"cheapest way to 90% by 7am, currently at 40%\" — and "
    "I'll give you the exact charge windows, the total cost, and how "
    "much you save versus charging straight away. No AI needed: the "
    "solver computes everything from your rates. An optional AI backend "
    "only explains the plan in free-form chat."
)

_PLAN_HINTS = ("cheapest", "charge", "by ", "%", "cost", "when should")
_TARGET_RE = re.compile(r"(?:to|reach|target(?: of)?)\s*(\d{1,3})\s*%", re.IGNORECASE)
_CURRENT_RE = re.compile(r"(?:currently|now|starting|from|at)\s*(?:at\s*)?(\d{1,3})\s*%", re.IGNORECASE)
_TIME_RE = re.compile(
    r"by\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)", re.IGNORECASE)


def parse_request(text: str, settings):
    """Best-effort read of (target_soc, current_soc, deadline_text)."""
    low = text.lower()
    target = settings.target_soc
    m = _TARGET_RE.search(low)
    if m:
        target = max(50, min(100, int(m.group(1))))
    current = settings.current_soc
    m2 = _CURRENT_RE.search(low)
    if m2 and (m is None or m2.start() != m.start()):
        # Avoid re-reading the target as the current level.
        if not (m and m2.group(1) == m.group(1) and m2.start() <= m.start()):
            current = max(0, min(100, int(m2.group(1))))
    deadline_text = settings.deadline
    m3 = _TIME_RE.search(low)
    if m3:
        raw = m3.group(1).replace(".", "")
        try:
            parse_time_12h(raw)
            deadline_text = raw
        except ValueError:
            pass
    return target, current, deadline_text


class ChargeOracleService:
    def __init__(self, settings, llm_factory=None, now_fn=None):
        self.settings = settings
        self.llm_factory = llm_factory
        self.now_fn = now_fn or datetime.now
        self.last_plan = None
        self.applied_actions: list[str] = []
        self._ids = itertools.count(1)

    def _llm(self):
        if self.llm_factory is not None:
            return self.llm_factory()
        if self.settings.ai_mode == "never" or not self.settings.ai_base_url:
            return None
        return LlmBackend(self.settings.ai_base_url, self.settings.ai_api_key,
                          self.settings.ai_model, self.settings.ai_timeout_seconds)

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}-{int(time.time())}-{next(self._ids)}"

    def make_plan(self, target=None, current=None, deadline_text=None,
                  vehicle=None, now=None):
        s = self.settings
        now = now or self.now_fn()
        target = s.target_soc if target is None else target
        current = s.current_soc if current is None else current
        deadline_text = s.deadline if deadline_text is None else deadline_text
        deadline = next_deadline(deadline_text, now)
        vehicle = vehicle or (s.vehicles[0].name if s.vehicles else "Model Y")
        plan = solve(vehicle, current, target, s.battery_kwh, s.charge_kw,
                     s.efficiency, RateTable.from_settings(s), now, deadline)
        self.last_plan = plan
        return plan

    def _vehicle_for(self, text: str) -> str:
        low = text.lower()
        for v in self.settings.vehicles:
            if v.name.lower() in low:
                return v.name
        if self.settings.vehicles:
            return self.settings.vehicles[0].name
        return "Model Y"

    def models_list(self) -> dict:
        return {"object": "list", "data": [{
            "id": self.settings.model_id, "object": "model",
            "created": int(time.time()), "owned_by": "tesla-charge-oracle",
        }]}

    def chat_completions(self, body: dict) -> dict:
        messages = body.get("messages") or []
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content") or ""
                user_text = str(content) if not isinstance(content, list) else " ".join(
                    str(p.get("text", "")) for p in content
                    if isinstance(p, dict) and p.get("type") == "text")
                break
        low = user_text.lower()
        if any(h in low for h in _PLAN_HINTS):
            target, current, deadline_text = parse_request(user_text, self.settings)
            plan = self.make_plan(target, current, deadline_text,
                                  self._vehicle_for(user_text))
            text = plan.summary()
        else:
            text = self._llm_answer(user_text)
        return {
            "id": self._next_id("chatcmpl"), "object": "chat.completion",
            "created": int(time.time()), "model": self.settings.model_id,
            "choices": [{"index": 0, "message": {"role": "assistant",
                                                "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                      "total_tokens": 0},
        }

    def embeddings(self, body: dict) -> dict:
        raw = body.get("input", "")
        texts = raw if isinstance(raw, list) else [raw]
        data = [{"object": "embedding", "index": i,
                 "embedding": embed_text(str(t), self.settings.embedding_dim)}
                for i, t in enumerate(texts)]
        return {"object": "list", "data": data, "model": self.settings.model_id,
                "usage": {"prompt_tokens": 0, "total_tokens": 0}}

    def _context(self) -> str:
        s = self.settings
        lines = [
            f"Rates: peak ${s.rate_peak:.2f}/kWh ({s.peak_start}–{s.peak_end}); "
            f"off-peak ${s.rate_offpeak:.2f}/kWh (until {s.offpeak_end}); "
            f"mid-peak ${s.rate_mid:.2f}/kWh otherwise. Charger "
            f"{s.charge_kw} kW, pack {s.battery_kwh} kWh, default target "
            f"{s.target_soc}% by {s.deadline}.",
        ]
        if self.last_plan is not None:
            lines.append("Latest plan:\n" + self.last_plan.summary())
        return "\n".join(lines)

    def _llm_answer(self, user_text: str) -> str:
        llm = self._llm()
        if llm is None:
            return CAPABILITY_BLURB
        try:
            reply = llm.chat(self._context(), user_text)
        except Exception:
            return CAPABILITY_BLURB + " (The AI backend didn't respond just now.)"
        cmd = extract_command(reply)
        if cmd is None:
            return reply
        vehicle = None
        needle = cmd["vehicle"].lower()
        for v in self.settings.vehicles:
            if needle in v.name.lower() or v.name.lower() in needle:
                vehicle = v
                break
        if vehicle is None:
            names = ", ".join(v.name for v in self.settings.vehicles) or "(none yet)"
            return (f"I couldn't match \"{cmd['vehicle']}\" to one of your "
                    f"cars. Your cars: {names}.")
        return self._execute_llm_command(cmd, vehicle)

    def _execute_llm_command(self, cmd: dict, vehicle) -> str:
        name = cmd["command"]
        params = cmd.get("params", {})
        if self.settings.dry_run:
            return f"Dry run: would run {name} for {vehicle.name} — nothing changed."
        if name == "plan_charge":
            target = params.get("target_soc") or self.settings.target_soc
            plan = self.make_plan(int(target), self.settings.current_soc,
                                  self.settings.deadline, vehicle.name)
            return plan.summary()
        if name == "set_charge_limit":
            limit = params.get("limit") or params.get("target_soc") or self.settings.target_soc
            action = f"Set charge limit to {limit}% for {vehicle.name}"
            self.applied_actions.append(action)
            return (action + ". (Recorded in this app; the Fleet API send "
                    "happens when you run `tcoracle apply` after pairing — "
                    "see README.)")
        if name in ("start_charging", "stop_charging"):
            action = f"{'Start' if name == 'start_charging' else 'Stop'} charging {vehicle.name}"
            self.applied_actions.append(action)
            return (action + ". (Recorded in this app; the Fleet API send "
                    "happens when you run `tcoracle apply` after pairing — "
                    "see README.)")
        return f"Unknown command {name} — dropped."
