"""Create the composite Firestore indexes declared at the repository root."""

import json
from pathlib import Path
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore_admin_v1

from app.config import settings

INDEX_MANIFEST = Path(__file__).resolve().parents[2] / "firestore.indexes.json"


def _declared_indexes() -> list[dict[str, Any]]:
    return json.loads(INDEX_MANIFEST.read_text(encoding="utf-8"))["indexes"]


def _signature(fields: list[Any]) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    for field in fields:
        field_path = field.field_path if hasattr(field, "field_path") else field["fieldPath"]
        if field_path == "__name__":
            continue
        if hasattr(field, "order"):
            order = firestore_admin_v1.Index.IndexField.Order(field.order).name
        else:
            order = field["order"]
        result.append((field_path, order))
    return tuple(result)


def main() -> None:
    if not settings.gcp_project:
        raise SystemExit("GCP_PROJECT is required")

    client = firestore_admin_v1.FirestoreAdminClient()
    database = f"projects/{settings.gcp_project}/databases/{settings.firestore_database}"
    operations = []
    created = 0
    existing = 0

    for declared in _declared_indexes():
        collection = declared["collectionGroup"]
        parent = f"{database}/collectionGroups/{collection}"
        wanted = _signature(declared["fields"])
        collection_path = f"/collectionGroups/{collection}/indexes/"
        present = {
            _signature(index.fields)
            for index in client.list_indexes(parent=parent)
            if collection_path in index.name
            and index.query_scope == firestore_admin_v1.Index.QueryScope[declared["queryScope"]]
        }
        if wanted in present:
            existing += 1
            continue

        fields = [
            firestore_admin_v1.Index.IndexField(
                field_path=field["fieldPath"],
                order=firestore_admin_v1.Index.IndexField.Order[field["order"]],
            )
            for field in declared["fields"]
        ]
        index = firestore_admin_v1.Index(
            query_scope=firestore_admin_v1.Index.QueryScope[declared["queryScope"]],
            fields=fields,
        )
        try:
            operations.append(client.create_index(parent=parent, index=index))
            created += 1
        except AlreadyExists:
            existing += 1

    for operation in operations:
        operation.result(timeout=600)

    print(f"Firestore indexes ready: {created} created, {existing} already present")


if __name__ == "__main__":
    main()
