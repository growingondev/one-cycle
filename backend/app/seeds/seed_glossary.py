from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.app.db.session import SessionLocal
from backend.app.models.glossary import Glossary


SEED_PATH = Path(__file__).with_name("glossary_seed.json")
REQUIRED_KEYS = {"term", "definition", "category", "is_active"}


def load_seed_data() -> list[dict]:
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ValueError("glossary seed data must be a JSON array")

    terms: set[str] = set()

    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"seed item #{index} must be an object")

        if set(item) != REQUIRED_KEYS:
            raise ValueError(
                f"seed item #{index} has invalid keys: {sorted(item)}"
            )

        term = item["term"]
        definition = item["definition"]
        category = item["category"]
        is_active = item["is_active"]

        if not isinstance(term, str) or not term.strip():
            raise ValueError(f"seed item #{index}: term is required")
        if not isinstance(definition, str) or not definition.strip():
            raise ValueError(f"seed item #{index}: definition is required")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"seed item #{index}: category is required")
        if not isinstance(is_active, bool):
            raise ValueError(f"seed item #{index}: is_active must be boolean")

        if term in terms:
            raise ValueError(f"duplicate term in seed data: {term}")
        terms.add(term)

    return data


def seed_glossary() -> None:
    data = load_seed_data()

    with SessionLocal() as db:
        before = db.scalar(
            select(func.count()).select_from(Glossary)
        ) or 0

        stmt = (
            pg_insert(Glossary)
            .values(data)
            .on_conflict_do_nothing(index_elements=[Glossary.term])
        )
        db.execute(stmt)
        db.commit()

        after = db.scalar(
            select(func.count()).select_from(Glossary)
        ) or 0

    print(f"seed_source_count={len(data)}")
    print(f"inserted_count={after - before}")
    print(f"glossary_total_count={after}")


if __name__ == "__main__":
    seed_glossary()
