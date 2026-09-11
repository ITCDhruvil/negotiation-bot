"""Lightweight inbound checks — not a full jailbreak product, enough for a priced POC."""

import re
import time
from collections import defaultdict

_JAILBREAK = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts)",
    r"reveal (your )?(system )?prompt",
    r"show (me )?(your )?instructions",
    r"developer mode",
    r"jailbreak",
    r"you are now dan",
    r"pretend (you are|to be) (a )?human",
    r"what is (the |your )?(floor|max acceptable|walk-away|ceiling)",
    r"minimum (price|you can go)|maximum you can pay",
    r"print your system",
]


def looks_like_jailbreak(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in _JAILBREAK)


class SlidingWindowLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self.max_per_minute = max_per_minute
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.time()
        window = now - 60
        hits = [stamp for stamp in self._hits[key] if stamp >= window]
        if len(hits) >= self.max_per_minute:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True
