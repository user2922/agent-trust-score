"""Shannon entropy, used by exactly one rule.

The generic secret rule (an assignment to a credential-shaped name) needs a way
to tell ``API_KEY = "the quick brown fox jumps"`` from
``API_KEY = "hunter2Xk9mQpZ4vL8nR3wY7"``. Provider patterns never consult this:
a well-formed AWS key is a hit whatever its entropy happens to be.
"""

from __future__ import annotations

import math
from collections import Counter

# Below this, a 20+ character string reads as prose or a repeated placeholder.
ENTROPY_THRESHOLD = 4.0


def shannon(value: str) -> float:
    """Bits of entropy per character.

    Returns 0.0 for the empty string. Uniform random base64 sits near 6.0;
    English prose sits near 4.0 and below, which is why the threshold is where
    it is -- and why the value allowlist does most of the real work.
    """
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def looks_random(value: str) -> bool:
    """True when ``value`` could be credential material.

    Entropy alone is not enough, and a pangram proves why: "the quick brown fox
    jumps over the lazy dog" uses every letter, so it scores *above* the
    threshold while being obviously prose. Credential material does not contain
    whitespace, so that structural test runs first and does most of the work.
    """
    if not value or any(character.isspace() for character in value):
        return False
    return shannon(value) >= ENTROPY_THRESHOLD
