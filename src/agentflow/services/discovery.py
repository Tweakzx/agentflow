from __future__ import annotations

from dataclasses import dataclass

from agentflow.store import Store


@dataclass
class DiscoveryResult:
    created: int
    skipped: int


class IssueDiscoveryService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def ingest_issues(self, project: str, issues: list[dict[str, object]]) -> DiscoveryResult:
        created = 0
        skipped = 0
        for issue in issues:
            ext = str(issue.get("number"))
            title = str(issue.get("title", f"issue-{ext}"))
            if self.store.get_task_by_external(project, "github", ext) is not None:
                skipped += 1
                continue
            self.store.add_task(
                project=project,
                title=title,
                description=str(issue.get("body", "")) or None,
                priority=int(issue.get("priority", 3)),
                impact=int(issue.get("impact", 3)),
                effort=int(issue.get("effort", 3)),
                source="github",
                external_id=ext,
            )
            created += 1
        return DiscoveryResult(created=created, skipped=skipped)
