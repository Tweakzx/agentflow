from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from collections.abc import Mapping, Sequence


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
        strict_allowlist: bool = True,
    ) -> None:
        self.timeout_sec = timeout_sec
        self.cwd = cwd
        self.allowed_prefixes = [p.strip() for p in (allowed_prefixes or []) if str(p).strip()]
        self.strict_allowlist = strict_allowlist

    def evaluate(self, commands: Sequence[object]) -> GateResult:
        checks: list[GateCheckResult] = []
        overall = True

        for command in commands:
            parsed = self._parse_command(command)
            if parsed is None:
                overall = False
                checks.append(
                    GateCheckResult(
                        command=self._command_label(command),
                        passed=False,
                        exit_code=2,
                        output=f"invalid gate command template: {self._command_label(command)}",
                    )
                )
                break
            argv, command_label = parsed

            if self.strict_allowlist and not self._is_allowed(argv):
                overall = False
                checks.append(
                    GateCheckResult(
                        command=command_label,
                        passed=False,
                        exit_code=126,
                        output=(
                            "blocked by gate allowlist (strict mode); "
                            "set AGENTFLOW_GATE_STRICT_ALLOWLIST=0 to opt out"
                        ),
                    )
                )
                break
            try:
                proc = subprocess.run(
                    argv,
                    shell=False,
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
                        command=command_label,
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
                        command=command_label,
                        passed=False,
                        exit_code=124,
                        output=f"timeout after {self.timeout_sec}s: {exc}",
                    )
                )
                break

        return GateResult(passed=overall, checks=checks)

    def _parse_command(self, command: object) -> tuple[list[str], str] | None:
        if isinstance(command, str):
            stripped = command.strip()
            if not stripped:
                return None
            argv = shlex.split(stripped)
            if not argv:
                return None
            return argv, stripped

        if isinstance(command, Mapping):
            raw_command = command.get("command")
            raw_args = command.get("args", [])
            if not isinstance(raw_command, str) or not raw_command.strip():
                return None
            if raw_args is None:
                args: list[str] = []
            elif isinstance(raw_args, Sequence) and not isinstance(raw_args, (str, bytes)):
                args = []
                for arg in raw_args:
                    if not isinstance(arg, str):
                        return None
                    args.append(arg)
            else:
                return None
            normalized = {
                "command": raw_command.strip(),
                "args": args,
            }
            return [normalized["command"], *args], json.dumps(normalized, separators=(",", ":"))

        return None

    def _is_allowed(self, argv: Sequence[str]) -> bool:
        if not self.allowed_prefixes:
            return False

        for prefix in self.allowed_prefixes:
            prefix_argv = shlex.split(prefix)
            if not prefix_argv:
                continue
            if list(argv[: len(prefix_argv)]) == prefix_argv:
                return True
        return False

    def _command_label(self, command: object) -> str:
        if isinstance(command, str):
            return command.strip() or repr(command)
        if isinstance(command, Mapping):
            return json.dumps(command, sort_keys=True, default=str)
        return repr(command)
