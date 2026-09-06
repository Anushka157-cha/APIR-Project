from __future__ import annotations

import hashlib
import math
from collections import deque


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def zscore(value: float, history: list[float]) -> float:
    s = stdev(history)
    if s == 0:
        return 0.0
    return (value - mean(history)) / s


def ewma(xs: list[float], alpha: float = 0.3) -> float:
    if not xs:
        return 0.0
    value = xs[0]
    for x in xs[1:]:
        value = alpha * x + (1 - alpha) * value
    return value


def moving_average(xs: list[float], window: int) -> float:
    if not xs:
        return 0.0
    chunk = xs[-window:]
    return mean(chunk)


class RollingWindow:
    def __init__(self, size: int = 60) -> None:
        self.size = size
        self.values: deque[float] = deque(maxlen=size)

    def add(self, value: float) -> None:
        self.values.append(value)

    def list(self) -> list[float]:
        return list(self.values)


def hashed_embedding(text: str, dims: int = 128) -> list[float]:
    """Deterministic bag-of-hashed-n-grams embedding for local RAG."""
    vec = [0.0] * dims
    lowered = text.lower()
    tokens = [t for t in "".join(ch if ch.isalnum() else " " for ch in lowered).split() if t]
    grams = tokens + ["".join(tokens[i : i + 2]) for i in range(len(tokens) - 1)]
    for g in grams:
        h = int(hashlib.sha256(g.encode()).hexdigest(), 16)
        vec[h % dims] += 1.0
        vec[(h // dims) % dims] -= 0.35
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
