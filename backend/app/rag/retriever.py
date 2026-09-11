"""Keyword grounding over the mock catalog. Swap for pgvector without touching the deal engine."""

from app.catalog import list_parts
from app.models import PartListing


def retrieve_grounding(query: str, listing: PartListing, k: int = 2) -> list[str]:
    tokens = {token.lower() for token in query.split() if len(token) > 3}
    scored: list[tuple[int, str]] = []
    for part in list_parts():
        blob = " ".join(
            [part.spec_blurb, part.part_name, part.category, part.vendor_name, part.plant]
        ).lower()
        score = sum(1 for token in tokens if token in blob)
        if part.part_id == listing.part_id:
            score += 2
        if score:
            scored.append((score, f"{part.part_name} ({part.vendor_name}): {part.spec_blurb}"))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [text for _, text in scored[:k]]
