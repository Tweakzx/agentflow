from __future__ import annotations

import os
import shlex
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


@dataclass
class ParsedGateCommand:
    argv: list[str]
    display: str


class GateEvaluator:
    def __init__(
        self,
        timeout_sec: int = 1800,
        *,
        cwd: str | None = None,
        allowed_prefixes: Sequence[str] | None = None,
        strict_mode: bool = True,
    ) -> None:
        self.timeout_sec = timeout_sec
        self.cwd = cwd
        self.allowed_prefixes = [p.strip() for p in (allowed_prefixes or []) if str(p).strip()]
        self.strict_mode = strict_mode

    def evaluate(self, commands: list[object]) -> GateResult:
        checks: list[GateCheckResult] = []
        overall = True

        for raw in commands:
            parsed = self._parse_command(raw)
            if parsed is None:
                overall = False
                checks.append(
                    GateCheckResult(
                        command=str(raw),
                        passed=False,
                        exit_code=126,
                        output="invalid gate command",
                    )
                )
                break
            if self.strict_mode and not self._is_allowed(parsed.argv[0]):
                overall = False
                checks.append(
                    GateCheckResult(
                        command=parsed.display,
                        passed=False,
                        exit_code=126,
                        output=f"blocked by gate allowlist: {parsed.argv[0]}",
                    )
                )
                break
            try:
                proc = subprocess.run(
                    parsed.argv,
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
                        command=parsed.display,
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
                        command=parsed.display,
                        passed=False,
                        exit_code=124,
                        output=f"timeout after {self.timeout_sec}s: {exc}",
                    )
                )
                break

        return GateResult(passed=overall, checks=checks)

    def _parse_command(self, raw: object) -> ParsedGateCommand | None:
        if isinstance(raw, str):
            parts = shlex.split(raw)
            if not parts:
                return None
            return ParsedGateCommand(argv=parts, display=raw)

        if not isinstance(raw, dict):
            return None
        command = raw.get("command")
        args = raw.get("args", [])
        if not isinstance(command, str) or not command.strip():
            return None
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            return None
        argv = [command, *args]
        display = " ".join(shlex.quote(x) for x in argv)
        return ParsedGateCommand(argv=argv, display=display)

    def _is_allowed(self, executable: str) -> bool:
        if not self.allowed_prefixes:
            return False
        bare = os.path.basename(executable)
        return executable in self.allowed_prefixes or bare in self.allowed_prefixes
