from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Sequence


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
    def __init__(
        self,
        timeout_sec: int = 1800,
        *,
        cwd: str | None = None,
        allowed_prefixes: Sequence[str] | None = None,
    ) -> None:
        self.timeout_sec = timeout_sec
        self.cwd = cwd
        self.allowed_prefixes = [p.strip() for p in (allowed_prefixes or []) if str(p).strip()]

    def evaluate(self, commands: list[str]) -> GateResult:
        checks: list[GateCheckResult] = []
        overall = True

        for command in commands:
            if self.allowed_prefixes and not self._is_allowed(command):
                overall = False
                checks.append(
                    GateCheckResult(
                        command=command,
                        passed=False,
                        exit_code=126,
                        output=f"blocked by gate allowlist: {command}",
                    )
                )
                break
            try:
                proc = subprocess.run(  # noqa: S602 - command source is project-controlled gate profile
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                    cwd=self.cwd,
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

    def _is_allowed(self, command: str) -> bool:
        stripped = command.strip()
        return any(stripped == p or stripped.startswith(f"{p} ") for p in self.allowed_prefixes)
