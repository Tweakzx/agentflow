from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class GateCheckResult:
    command: str
    passed: bool
    exit_code: int
    output: str


@dataclass
class GateResult:
    passed: bool
    checks: list[GateCheckResult]


class GateEvaluator:
    def __init__(self, timeout_sec: int = 1800) -> None:
        self.timeout_sec = timeout_sec

    def evaluate(self, commands: list[str]) -> GateResult:
        checks: list[GateCheckResult] = []
        overall = True

        for command in commands:
            try:
                proc = subprocess.run(  # noqa: S602 - command source is project-controlled gate profile
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                )
                passed = proc.returncode == 0
                if not passed:
                    overall = False
                output = (proc.stdout or "") + (proc.stderr or "")
                checks.append(
                    GateCheckResult(
                        command=command,
                        passed=passed,
                        exit_code=proc.returncode,
                        output=output.strip(),
                    )
                )
                if not passed:
                    break
            except subprocess.TimeoutExpired as exc:
                overall = False
                checks.append(
                    GateCheckResult(
                        command=command,
                        passed=False,
                        exit_code=124,
                        output=f"timeout after {self.timeout_sec}s: {exc}",
                    )
                )
                break

        return GateResult(passed=overall, checks=checks)
