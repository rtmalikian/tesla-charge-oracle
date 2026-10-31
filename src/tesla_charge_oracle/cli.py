"""CLI: tcoracle setup | serve | plan | preview | apply | simulate"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

from .config import ConfigError, load_settings

__version__ = "0.1.0"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")


def _service(settings):
    from .service import ChargeOracleService
    return ChargeOracleService(settings)


def cmd_setup(args, settings) -> int:
    from .setup import run_setup
    run_setup()
    return 0


def cmd_serve(args, settings) -> int:
    from .server import serve
    service = _service(settings)
    print("Vehicle data goes ONLY to your configured LLM backend "
          f"(TCO_AI_BASE_URL={settings.ai_base_url or 'none'}).")
    serve(service)
    return 0


def _plan_from_args(args, settings):
    service = _service(settings)
    vehicle = args.vehicle or (
        settings.vehicles[0].name if settings.vehicles else "Model Y")
    target = args.target if args.target is not None else settings.target_soc
    current = args.current if args.current is not None else settings.current_soc
    deadline = args.by or settings.deadline
    return service, service.make_plan(target, current, deadline, vehicle)


def cmd_plan(args, settings) -> int:
    _service_, plan = _plan_from_args(args, settings)
    print(plan.summary())
    return 0


def cmd_preview(args, settings) -> int:
    _service_, plan = _plan_from_args(args, settings)
    print("PREVIEW — nothing has been sent to any car, nothing changed.")
    print("")
    print(plan.summary())
    print("")
    print("Happy with that? Run `tcoracle apply` with the same options "
          "to record the plan for execution after pairing.")
    return 0


def cmd_apply(args, settings) -> int:
    service, plan = _plan_from_args(args, settings)
    print(plan.summary())
    print("")
    if not plan.windows:
        print("Nothing to apply.")
        return 0
    if not args.yes:
        answer = input("Apply this plan (record it for the car)? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("Not applied — nothing changed.")
            return 0
    service.applied_actions.append(
        f"Applied plan for {plan.vehicle}: {len(plan.windows)} window(s), "
        f"${plan.total_cost:.2f}")
    print("Plan recorded. Fleet API sends happen once a car is paired — "
          "see README 'Tesla developer setup'.")
    return 0


def cmd_simulate(_args, settings) -> int:
    from .simulator import render_demo, run_demo
    print(render_demo(run_demo(settings)))
    return 0


def _add_plan_args(p):
    p.add_argument("--vehicle", default=None,
                   help="Car nickname (default: first car in your settings)")
    p.add_argument("--target", type=int, default=None,
                   help="Target battery percent (default: your setting)")
    p.add_argument("--current", type=int, default=None,
                   help="Current battery percent (default: your setting)")
    p.add_argument("--by", default=None,
                   help="Deadline, e.g. '7:00 AM' (default: your setting)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tcoracle",
        description="Charge Oracle — the cheapest way to charge your Tesla "
                    "to a target level by a time you pick.")
    p.add_argument("--version", action="version", version=f"tcoracle {__version__}")
    p.add_argument("--env-file", default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Guided first-run setup (plain-language questions)")
    sub.add_parser("serve", help="Run the OpenAI-compatible API server")
    plan = sub.add_parser("plan", help="Print your cheapest charge plan")
    _add_plan_args(plan)
    prev = sub.add_parser("preview", help="Plain-English dry run (changes nothing)")
    _add_plan_args(prev)
    app = sub.add_parser("apply", help="Record the plan for execution (asks first)")
    _add_plan_args(app)
    app.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    sub.add_parser("simulate", help="Demo with pretend cars and rates (no API calls)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
    else:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    try:
        settings = load_settings(dict(os.environ))
    except ConfigError as exc:
        print(f"Config problem: {exc}", file=sys.stderr)
        return 2
    handlers = {"setup": cmd_setup, "serve": cmd_serve, "plan": cmd_plan,
                "preview": cmd_preview, "apply": cmd_apply,
                "simulate": cmd_simulate}
    try:
        return handlers[args.command](args, settings)
    except Exception as exc:  # human error messages, never a stack trace
        print(f"Something went wrong: {exc}. Check your settings with "
              "`tcoracle setup`, then try again.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
