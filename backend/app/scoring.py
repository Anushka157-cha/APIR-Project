from __future__ import annotations

from app.dependency_graph import affected_from, impact_rank


def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_hypothesis(
    *,
    name: str,
    metric_signals: list[dict],
    log_signals: list[dict],
    rag_hits: list[dict],
    origin_service: str,
    mentioned_services: list[str],
) -> dict:
    evidence = []
    contradicting = []
    metric_score = 0.0
    for m in metric_signals:
        change = abs(m.get("change_percent") or 0)
        related = origin_service in (m.get("service") or "") or m.get("service") in mentioned_services
        if change >= 50 and related:
            metric_score += min(change / 400.0, 0.35)
            evidence.append(m)
        elif change < 10:
            contradicting.append(m)
    log_score = 0.0
    for lg in log_signals:
        freq = lg.get("frequency") or 0
        if origin_service in (lg.get("service") or "") or any(
            k in (lg.get("pattern") or "").lower() for k in name.lower().split()
        ):
            log_score += min(freq / 40.0, 0.3)
            evidence.append(lg)
    rag_score = 0.0
    for hit in rag_hits:
        if any(tok in hit.get("document", "").lower() for tok in name.lower().replace("_", " ").split()[:3]):
            rag_score += min(hit.get("relevance_score") or 0, 0.25)
            evidence.append({"rag": hit.get("document"), "score": hit.get("relevance_score")})
    dep_score = 0.15 if origin_service in mentioned_services or not mentioned_services else 0.05
    if origin_service in affected_from(origin_service):
        dep_score += 0.05
    confidence = clamp(0.15 + metric_score + log_score + rag_score + dep_score)
    return {
        "hypothesis": name,
        "confidence": round(confidence, 2),
        "evidence": evidence[:8],
        "contradicting_evidence": contradicting[:4],
        "affected_services": [r["service"] for r in impact_rank(origin_service)],
        "score_parts": {
            "metric": round(metric_score, 3),
            "logs": round(log_score, 3),
            "rag": round(rag_score, 3),
            "dependency": round(dep_score, 3),
        },
    }


def rank_hypotheses(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda h: h["confidence"], reverse=True)
