"""Run: python -m app.harness  (from backend/, real LLM required)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["USE_IN_MEMORY"] = "true"
os.environ.pop("ARIA_ALLOW_MOCK", None)


def main() -> None:
    from app.harness.personas import SCENARIOS
    from app.harness.runner import format_report, run_harness, write_outputs

    parser = argparse.ArgumentParser(description="Aria live negotiation harness vs simulated vendors")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        choices=list(SCENARIOS),
        help="Repeatable. Default: all scenarios including ₹10L and floor-probe guardrails.",
    )
    parser.add_argument("--max-turns", type=int, default=12)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    results = asyncio.run(run_harness(args.scenarios, max_turns=args.max_turns))
    out_dir = BACKEND_ROOT / "harness" / "results"
    json_path, txt_path = write_outputs(results, out_dir)
    sys.stdout.reconfigure(encoding="utf-8")
    print(format_report(results))
    print(f"Wrote {txt_path}")
    print(f"Wrote {json_path}")
    raise SystemExit(1 if any(r.error for r in results) else 0)


if __name__ == "__main__":
    main()
