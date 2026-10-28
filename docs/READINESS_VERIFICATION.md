# Readiness verification

Scope: local Agentarium recorder and dashboard. No paid model calls or public
deployment were used for these checks.

The supported SDK range is `openai-agents>=0.24,<0.25`. Full payload capture
requires an explicit opt in, and simultaneous recorders cannot truncate the
same active event file. The Python suite includes regressions for both controls.

The fixes add regression coverage for current model-call context (including tool
results), structured final outputs, preservation of workflow exceptions when
recording fails, credential redaction, capture controls, a private-data export
fixture, callback serialization failures, and incremental JSONL reading across
partial writes, truncation, and file replacement.

The local verification run passed 43 Python tests, 17 JavaScript tests, and the
five checks reported by the headless-browser suite (including its parent test).
CI now includes the browser suite and a fresh wheel-installation check; that
remote CI run has not been executed as part of this local session.
The large-recording time and memory benchmarks are also in CI. The measured
workload is 10,000 events with 4 KB per event, about a 44 MB recording; it is
the supported local performance target, not a cap on input size.

The 2026-10-28 follow-up used Python 3.11.18 with Agents SDK 0.24.0. A wheel
was built from the current worktree and installed with its declared dependencies
in a fresh temporary virtual environment. The installed-package check passed,
including import, dashboard assets, CLI, and `pip check`. The old
`.venv-agentarium` environment has SDK 0.22.2
and fails during SDK import; recreate it from the declared dependencies before
using it for development.
Running the source test directory from outside the checkout in that clean
environment loaded 39 tests; its one import error was the test module that
imports the source-only `examples` directory. The complete 40-test suite passed
from the checkout with the supported development environment.

## Performance checks

Measured locally on 2026-10-28 with synthetic, non-sensitive data:

| Check | Workload | Observed | Target |
|---|---|---|---|
| Frontend model | 10,002 events; 40,960,000 payload bytes | 3.75 ms; 138,119,816-byte heap | <1,000 ms; <256 MiB heap |
| File reader | 10,000 events; 44,010,564-byte file | 2.387 seconds; 1,693,655-byte peak allocation | <10 seconds; <128 MiB peak allocation |
| Completed file at idle | 100 polls | 0 additional content bytes read | 0 |

Run `node tools/benchmark_run_view.cjs` and
`python -m tools.benchmark_event_tail` to reproduce. The browser renders trace
pages of at most 200 rows and batches incoming event updates every 100 ms.
Individual full payloads still require memory proportional to their size.

## Installed package check

A wheel was built without build isolation, installed with its declared
dependencies into a fresh temporary Python 3.11 virtual environment, and imported
from outside the repository. Packaged frontend assets and the console command
were present, `pip check` passed, and 17 recorder/adapter tests passed against the
installed wheel. This also checked a newer SDK dependency set than the existing
development environment.

To repeat for a release, build a wheel, create a fresh virtual environment,
install that wheel normally, and run the following with the new environment's
interpreter while the working directory is outside this repository:

```bash
python /absolute/path/to/agentarium/tools/verify_installed.py
```

This check verifies installation and local assets. It does not establish public
deployment status, compatibility with every SDK version, or model-answer quality.
