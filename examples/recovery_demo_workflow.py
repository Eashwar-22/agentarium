"""A controlled failure-and-recovery demo for Agentarium.

The local lookup tool reports two retryable failures, then succeeds on the
third call. OpenAI is used only to drive the agent; Tavily is not used.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass

from agents import Agent, function_tool

from agentarium import load_env_file, observe_openai
from agentarium.core import EventRecorder


DEFAULT_REQUEST = "Find a short, safe summary of the recovery demo result."


@dataclass
class RecoveryRuntime:
    """Local state for one deterministic demo run."""

    recorder: EventRecorder
    agent_id: str
    attempts: int = 0

    def lookup(self, topic: str) -> str:
        self.attempts += 1
        if self.attempts < 3:
            message = f"Temporary catalog lookup failure ({self.attempts} of 2)."
            self.recorder.record_error(
                message,
                self.agent_id,
                code="temporary_catalog_failure",
                retryable=True,
            )
            self.recorder.record_retry(
                self.agent_id,
                "Recovery Scout will retry the local catalog lookup.",
                attempt=self.attempts + 1,
            )
            return json.dumps(
                {
                    "ok": False,
                    "retryable": True,
                    "message": message,
                    "next_attempt": self.attempts + 1,
                }
            )

        return json.dumps(
            {
                "ok": True,
                "result": f"Recovered catalog result for: {topic}",
                "attempt": self.attempts,
            }
        )


active_runtime: RecoveryRuntime | None = None


@function_tool
def unstable_catalog_lookup(topic: str) -> str:
    """Look up a local catalog entry that recovers after two temporary failures.

    Args:
        topic: The subject to look up.
    """

    if active_runtime is None:
        raise RuntimeError("The recovery demo has not started.")
    return active_runtime.lookup(topic)


recovery_scout = Agent(
    name="Recovery Scout",
    instructions=(
        "Use unstable_catalog_lookup to investigate the request. The first two "
        "responses are retryable failures. Keep retrying until the tool returns "
        '"ok": true, then report only the successful result in one sentence.'
    ),
    tools=[unstable_catalog_lookup],
)


recovery_reporter = Agent(
    name="Recovery Reporter",
    instructions=(
        "Write a two-sentence user-safe incident summary. State that the local "
        "lookup recovered after retrying, then give the successful result. Do "
        "not invent technical details."
    ),
)


def _require_key() -> None:
    load_env_file()
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Load your existing .env file before running this demo."
        )


def _show(stage: str, value: object) -> None:
    print(f"\n{'=' * 12} {stage} {'=' * 12}")
    print(value)


async def run_recovery_demo(request: str) -> str:
    """Run a real agent around a local tool that fails twice then recovers."""

    global active_runtime
    _require_key()
    _show("REQUEST", request)

    async with observe_openai(request, show_dashboard=True) as observed:
        scout_id = observed.hooks.identify(recovery_scout)
        active_runtime = RecoveryRuntime(observed.recorder, scout_id)
        try:
            scout_result = await observed.run(recovery_scout, request, max_turns=8)
            recovered_result = str(scout_result.final_output)
            _show("RECOVERY SCOUT", recovered_result)

            report_result = await observed.run(
                recovery_reporter,
                f"Request: {request}\n\nRecovered result: {recovered_result}",
                max_turns=3,
            )
            report = str(report_result.final_output)
            _show("RECOVERY REPORT", report)
            return report
        finally:
            active_runtime = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Agentarium's controlled failure-and-recovery demo."
    )
    parser.add_argument("request", nargs="*", help="Optional lookup request.")
    args = parser.parse_args()
    request = " ".join(args.request).strip() or DEFAULT_REQUEST

    try:
        asyncio.run(run_recovery_demo(request))
    except KeyboardInterrupt:
        raise SystemExit("\nStopped by user.") from None
    except Exception as exc:
        raise SystemExit(f"\nRecovery demo failed: {exc}") from exc


if __name__ == "__main__":
    main()
