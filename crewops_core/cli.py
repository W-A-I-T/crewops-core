from __future__ import annotations

import argparse
import json

from crewops_core.runtime import get_runtime


def _default_departments() -> None:
    runtime = get_runtime()
    if runtime.departments:
        return
    runtime.register_department("software", lambda request: f"[software] drafted response for: {request}")
    runtime.register_department("research", lambda request: f"[research] collected notes for: {request}")
    runtime.register_department("operations", lambda request: f"[operations] queued next steps for: {request}")


def main() -> None:
    _default_departments()
    runtime = get_runtime()

    parser = argparse.ArgumentParser(description="crewops-core local-first agent runtime")
    parser.add_argument("--dept", default="software", help="Registered department to run.")
    parser.add_argument("--request", help="Request text to execute.")
    parser.add_argument("--list-depts", action="store_true", help="Print registered departments and exit.")
    args = parser.parse_args()

    if args.list_depts:
        print(json.dumps(runtime.list_departments(), indent=2))
        return
    if not args.request:
        parser.error("--request is required unless --list-depts is set")

    result = runtime.dispatch(args.dept, args.request)
    print(result)


if __name__ == "__main__":
    main()
