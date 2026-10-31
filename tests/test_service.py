from datetime import datetime

from tesla_charge_oracle.config import Settings, VehicleConfig
from tesla_charge_oracle.llm import extract_command
from tesla_charge_oracle.service import ChargeOracleService, parse_request


def _service(**over):
    settings = Settings(vehicles=[VehicleConfig("Model Y", "VINY")],
                        ai_mode="never", **over)
    return ChargeOracleService(settings,
                               now_fn=lambda: datetime(2026, 10, 31, 18, 0))


def _chat(service, text):
    return service.chat_completions(
        {"model": "tesla-charge-oracle",
         "messages": [{"role": "user", "content": text}]})["choices"][0]["message"]["content"]


def test_chat_plan_from_plain_language():
    svc = _service()
    text = _chat(svc, "cheapest way to 90% by 7am, currently at 40%")
    assert "90%" in text and "$" in text
    assert svc.last_plan is not None and svc.last_plan.achieved


def test_chat_plan_defaults():
    svc = _service()
    text = _chat(svc, "what is the cheapest way to charge?")
    assert "90%" in text  # default target from settings


def test_parse_request_variants():
    s = Settings()
    target, current, deadline = parse_request(
        "cheapest way to 80% by 6am, currently at 30%", s)
    assert (target, current) == (80, 30)
    assert deadline == "6am"
    target, current, _ = parse_request("charge to 100% by 8:00 AM", s)
    assert target == 100


def test_capability_blurb_without_plan_words():
    svc = _service()
    text = _chat(svc, "hello, what can you do?")
    assert "cheapest way" in text


def test_models_and_embeddings_shapes():
    svc = _service()
    models = svc.models_list()
    assert models["object"] == "list"
    assert models["data"][0]["id"] == "tesla-charge-oracle"
    emb = svc.embeddings({"input": "cheap overnight charging"})
    assert emb["object"] == "list"
    assert len(emb["data"][0]["embedding"]) == 384
    assert emb["data"][0]["embedding"] != [0.0] * 384
    emb2 = svc.embeddings({"input": "cheap overnight charging"})
    assert emb["data"][0]["embedding"] == emb2["data"][0]["embedding"]


def test_llm_command_allowlist():
    good = extract_command(
        '```json\n{"command": "set_charge_limit", "vehicle": "Model Y", '
        '"params": {"limit": 90}}\n```')
    assert good and good["command"] == "set_charge_limit"
    bad = extract_command(
        '```json\n{"command": "unlock_doors", "vehicle": "Model Y"}\n```')
    assert bad is None
    assert extract_command("no block here") is None


def test_llm_command_execution_and_dry_run():
    svc = _service()
    svc.llm_factory = lambda: _FakeLlm(
        '```json\n{"command": "set_charge_limit", "vehicle": "Model Y", '
        '"params": {"limit": 85}}\n```')
    svc.settings.ai_mode = "always"
    text = _chat(svc, "set my limit please")
    assert "85%" in text
    dry = _service(dry_run=True)
    dry.llm_factory = lambda: _FakeLlm(
        '```json\n{"command": "start_charging", "vehicle": "Model Y"}\n```')
    dry.settings.ai_mode = "always"
    assert "Dry run" in _chat(dry, "start charging please")
    assert dry.applied_actions == []


class _FakeLlm:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, context, user_message):
        return self.reply
