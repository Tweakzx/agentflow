from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

EVENT_FAMILIES: tuple[str, ...] = ("dispatch", "execution", "governance", "feedback", "risk")
VALID_SEVERITIES: tuple[str, ...] = ("info", "warning", "error")

EVENT_TYPES_BY_FAMILY: dict[str, tuple[str, ...]] = {
    "dispatch": (
        "task.claimed",
        "task.released",
        "task.reassigned",
        "task.takeover_started",
        "task.automation_resumed",
    ),
    "execution": (
        "run.started",
        "run.finished",
        "step.started",
        "step.passed",
        "step.failed",
    ),
    "governance": (
        "task.status_changed",
        "lease.extended",
        "lease.reclaimed",
        "task.force_moved",
    ),
    "feedback": (
        "progress.reported",
        "handoff.recorded",
        "comment.received",
        "comment.published",
        "pr.synced",
    ),
    "risk": (
        "gate.failed",
        "gate.passed",
        "task.blocked",
        "task.conflict_detected",
        "run.dead_lettered",
    ),
}

_EVENT_TYPE_TO_FAMILY = {event_type: family for family, event_types in EVENT_TYPES_BY_FAMILY.items() for event_type in event_types}
_SUMMARY_RISK_EVENT_TYPES = {"gate.failed", "task.blocked", "task.conflict_detected", "run.dead_lettered"}


def validate_event_family(event_family: str) -> str:
    if event_family not in EVENT_FAMILIES:
        raise ValueError(f"Unsupported event family: {event_family}")
    return event_family


def validate_event_type(event_family: str, event_type: str) -> str:
    validate_event_family(event_family)
    if _EVENT_TYPE_TO_FAMILY.get(event_type) != event_family:
        raise ValueError(f"Unsupported event type for {event_family}: {event_type}")
    return event_type


def validate_severity(severity: str) -> str:
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Unsupported severity: {severity}")
    return severity


def _clean_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value) if value else {}


def build_event(
    *,
    event_family: str,
    event_type: str,
    actor_type: str,
    summary: str,
    severity: str = "info",
    task_id: int | None = None,
    run_id: int | None = None,
    trigger_id: int | None = None,
    parent_event_id: int | None = None,
    actor_id: str | None = None,
    source_type: str | None = None,
    source_ref: str | None = None,
    status_from: str | None = None,
    status_to: str | None = None,
    run_status_from: str | None = None,
    run_status_to: str | None = None,
    evidence: Mapping[str, Any] | None = None,
    next_action: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    occurred_at: str | None = None,
    recorded_at: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    validate_event_type(event_family, event_type)
    validate_severity(severity)

    event: dict[str, Any] = {
        "event_family": event_family,
        "event_type": event_type,
        "actor_type": actor_type,
        "summary": summary,
        "severity": severity,
        "evidence": _clean_mapping(evidence),
        "next_action": _clean_mapping(next_action),
        "context": _clean_mapping(context),
    }

    optional_values = {
        "task_id": task_id,
        "run_id": run_id,
        "trigger_id": trigger_id,
        "parent_event_id": parent_event_id,
        "actor_id": actor_id,
        "source_type": source_type,
        "source_ref": source_ref,
        "status_from": status_from,
        "status_to": status_to,
        "run_status_from": run_status_from,
        "run_status_to": run_status_to,
        "occurred_at": occurred_at,
        "recorded_at": recorded_at,
        "idempotency_key": idempotency_key,
    }
    event.update({key: value for key, value in optional_values.items() if value is not None})
    return event


def build_gate_failed_event(
    *,
    task_id: int | None,
    run_id: int | None,
    actor_id: str | None,
    summary: str,
    error_code: str,
    log_excerpt: str | None = None,
    next_action: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "step_name": "gate",
        "error_code": error_code,
    }
    if log_excerpt is not None:
        evidence["log_excerpt"] = log_excerpt

    default_next_action = next_action or {"recommended": "takeover"}
    return build_event(
        event_family="risk",
        event_type="gate.failed",
        actor_type="system",
        actor_id=actor_id,
        task_id=task_id,
        run_id=run_id,
        summary=summary,
        severity="error",
        evidence=evidence,
        next_action=default_next_action,
        context=context,
    )


def derive_task_summary(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    event_list = list(events)

    latest_progress = _latest_event(event_list, {"progress.reported"})
    latest_handoff = _latest_event(event_list, {"handoff.recorded"})
    latest_risk = _latest_event(event_list, _SUMMARY_RISK_EVENT_TYPES)

    recommended_source = latest_risk or latest_handoff or latest_progress
    recommended_actions = _recommended_actions_from_event(recommended_source)

    return {
        "latest_progress": latest_progress,
        "latest_handoff": latest_handoff,
        "latest_risk": latest_risk,
        "recommended_actions": recommended_actions,
    }


def _latest_event(events: Iterable[Mapping[str, Any]], event_types: set[str]) -> dict[str, Any] | None:
    latest_event: dict[str, Any] | None = None
    latest_key: tuple[datetime, datetime, int, int] | None = None
    for index, event in enumerate(events):
        event_type = str(event.get("event_type", ""))
        if event_type not in event_types:
            continue
        candidate = dict(event)
        candidate_key = _event_sort_key(candidate, index)
        if latest_key is None or candidate_key > latest_key:
            latest_event = candidate
            latest_key = candidate_key
    return latest_event


def _event_sort_key(event: Mapping[str, Any], index: int) -> tuple[datetime, datetime, int, int]:
    occurred_at = _parse_datetime(event.get("occurred_at"))
    recorded_at = _parse_datetime(event.get("recorded_at"))
    event_id = _coerce_int(event.get("id"))
    return occurred_at, recorded_at, event_id, index


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            pass
    return datetime.min


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _recommended_actions_from_event(event: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not event:
        return []

    next_action = event.get("next_action")
    if not isinstance(next_action, Mapping):
        return []

    actions = next_action.get("actions")
    if isinstance(actions, list):
        normalized_actions: list[dict[str, Any]] = []
        for action in actions:
            if isinstance(action, Mapping):
                normalized_actions.append(dict(action))
        if normalized_actions:
            return normalized_actions

    recommended = next_action.get("recommended")
    if isinstance(recommended, str) and recommended.strip():
        label = recommended.replace("_", " ").strip().title()
        return [{"id": recommended, "label": label}]

    return []
