"""python -m app.finetune preview|export|tick|submit|status"""

from __future__ import annotations

import json
import sys


def main() -> int:
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").strip().lower()
    if cmd == "preview":
        from app.finetune.export import preview_dataset

        print(json.dumps(preview_dataset(), indent=2))
        return 0
    if cmd == "export":
        from app.finetune.export import export_dataset

        print(json.dumps(export_dataset(), indent=2))
        return 0
    if cmd in {"tick", "status"}:
        from app.finetune.pipeline import status, tick

        print(json.dumps(tick() if cmd == "tick" else status(), indent=2, default=str))
        return 0
    if cmd == "submit":
        from app.finetune.pipeline import tick

        print(json.dumps(tick(force=True), indent=2, default=str))
        return 0
    print("Usage: python -m app.finetune preview|export|tick|submit|status")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
