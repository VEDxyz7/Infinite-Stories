"""Explicit local inference diagnostics; no hosted/provider calls or credentials.

Reuses unchanged acceptance predicates and historical Qloo fixtures. Captures
only the loopback model's JSON request/response, never HTTP headers. Output must
be private (reports/local) and new. This is not production request logging.
"""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from backend.app.config import Settings
from backend.app.content import make_chapter
from backend.app.engine import game_view
from backend.app.local_game_master import OllamaGameMaster
from backend.app.models import CulturalEvidenceReply, DomainError
from scripts import evaluate_local_game_master as evaluation


class TraceTransport(httpx.AsyncBaseTransport):
    def __init__(self, traces):
        self.traces = traces
        self.inner = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        trace = {"input": json.loads(request.content)}
        self.traces.append(trace)
        response = await self.inner.handle_async_request(request)
        trace["http_status"] = response.status_code
        trace["output"] = json.loads(await response.aread())
        return response

    async def aclose(self):
        await self.inner.aclose()


async def run(model, repeats, controls=False):
    traces, results = [], []

    class TracedGameMaster(OllamaGameMaster):
        async def run(self, *args):
            requests = []
            self.transport = TraceTransport(requests)
            try:
                return await super().run(*args)
            finally:
                traces.append({"requests": requests, **(requests[0] if requests else {})})

    evaluation.OllamaGameMaster = TracedGameMaster
    for repeat in range(repeats):
        rows = await evaluation.evaluate_grounding(model)
        for row, trace in zip(rows, traces[-len(rows) :], strict=True):
            row.update(repeat=repeat + 1, trace=trace)
        results.extend(rows)
    control_results = []
    journey = None
    if controls:
        gm = TracedGameMaster(Settings(llm_provider="ollama", llm_model=model, llm_calls_allowed=True))
        for name, text, scenario, expected in evaluation.CASES:
            state = evaluation.state_for(scenario)
            try:
                reply = await gm.run(make_chapter(), game_view(make_chapter(), state, "control", 0, ""), text)
                command, narrative = reply
                passed = not isinstance(reply, CulturalEvidenceReply) and (
                    command is None
                    if expected is None
                    else command is not None and command.kind == "choose" and command.choice == expected
                )
                row = {"case": name, "pass": passed, "narrative": narrative}
            except DomainError as error:
                row = {"case": name, "pass": False, "error": error.code}
            row["trace"] = traces[-1]
            control_results.append(row)
            print("control_" + name, "PASS" if row["pass"] else "FAIL", flush=True)
        try:
            journey = evaluation.persistent_journey(model)
        except (AssertionError, DomainError) as error:
            journey = {"pass": False, "error": str(error)[:200]}
        print("authored_continuity_journey", "PASS" if journey["pass"] else "FAIL", flush=True)
    return {
        "kind": "actual_local_inference_diagnostic",
        "model": model,
        "cases": results,
        "passed": sum(r["pass"] for r in results),
        "total": len(results),
        "controls": control_results,
        "authored_journey": journey,
        "journey_traces": traces[len(results) + len(control_results) :],
        "live_qloo_calls": 0,
        "hosted_inference_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--repeats", type=int, default=1, choices=range(1, 6))
    parser.add_argument(
        "--controls",
        action="store_true",
        help="Also check ordinary intents and the unchanged authored continuity journey",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    private = Path("reports/local").resolve()
    if not args.output.resolve().is_relative_to(private) or args.output.exists():
        raise SystemExit("Use a new private reports/local output path")
    report = asyncio.run(run(args.model, args.repeats, args.controls))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        args.output.chmod(0o600)
        handle.write(json.dumps(report, indent=2) + "\n")
    print(f"{report['passed']}/{report['total']} actual local grounding checks")
    if (
        report["passed"] != report["total"]
        or any(not r["pass"] for r in report["controls"])
        or (report["authored_journey"] is not None and not report["authored_journey"]["pass"])
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
