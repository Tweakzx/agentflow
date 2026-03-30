from __future__ import annotations

from agentflow.store import Store


class TriggerService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def register_trigger(
        self,
        *,
        project: str,
        trigger_type: str,
        trigger_ref: str,
        idempotency_key: str,
        payload: str | None,
    ) -> dict[str, object]:
        existing = self.store.get_trigger_by_key(idempotency_key)
        if existing is not None:
            return {"duplicate": True, "trigger_id": int(existing["id"]) }

        trigger_id = self.store.upsert_trigger(
            project=project,
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        return {"duplicate": False, "trigger_id": trigger_id}
