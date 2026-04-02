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
        trigger_id, duplicate = self.store.register_trigger_once(
            project=project,
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        return {"duplicate": duplicate, "trigger_id": trigger_id}
