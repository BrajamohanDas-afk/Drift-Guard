import argparse
import asyncio
import json
import statistics
import time
from typing import Any

from app.workers.nightly_scan import nightly_scan


async def _run_iteration(index: int) -> dict[str, Any]:
    started_at = time.perf_counter()
    result = await nightly_scan({})
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {
        "iteration": index,
        "duration_ms": duration_ms,
        "result": result,
    }


async def _main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the nightly_scan worker task repeatedly for local load testing."
        )
    )
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    if args.iterations < 1:
        raise SystemExit("--iterations must be >= 1")
    if args.delay_seconds < 0:
        raise SystemExit("--delay-seconds must be >= 0")

    results: list[dict[str, Any]] = []
    failures = 0

    for index in range(1, args.iterations + 1):
        try:
            result = await _run_iteration(index)
        except Exception as exc:
            failures += 1
            result = {
                "iteration": index,
                "error": type(exc).__name__,
                "message": str(exc),
            }
            print(json.dumps(result, sort_keys=True))
            if args.fail_fast:
                break
        else:
            results.append(result)
            print(json.dumps(result, sort_keys=True))

        if args.delay_seconds and index < args.iterations:
            await asyncio.sleep(args.delay_seconds)

    durations = [item["duration_ms"] for item in results]
    summary = {
        "iterations_requested": args.iterations,
        "iterations_completed": len(results),
        "failures": failures,
        "duration_ms_min": min(durations) if durations else None,
        "duration_ms_max": max(durations) if durations else None,
        "duration_ms_mean": round(statistics.mean(durations), 2)
        if durations
        else None,
    }
    print(json.dumps({"summary": summary}, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
