from __future__ import annotations

from ai_fluency_collector.gitlab_scoring import _rate_context

# Review behavioral metrics → skill mappings.
# score_fn takes the computed metric rate (float 0.0–1.0) and returns int 0–100.
GITHUB_REVIEW_SKILL_MAPPINGS: dict[str, list[dict]] = {
    "lgtm_without_comment": [
        {"skill_id": "tg-code-review", "score_fn": lambda rate: round(100 - (rate * 100))},
    ],
    "review_comment_depth": [
        {"skill_id": "cq-evaluation", "score_fn": lambda ratio: round(ratio * 100)},
    ],
    "ai_coauthor_rate": [
        {"skill_id": "im-chat", "score_fn": lambda rate: round(rate * 100)},
    ],
    "ai_agent_coauthor_rate": [
        {"skill_id": "im-supervised-agent", "score_fn": lambda rate: round(rate * 100)},
    ],
    "self_review_rate": [
        {"skill_id": "cq-refinement", "score_fn": lambda rate: round(rate * 100)},
    ],
}


def calculate_github_review_scores(metrics, mappings: dict) -> list[dict]:
    """Calculate skill signals from GitHub PR review behavioral metrics.

    Args:
        metrics: GitHubReviewMetrics from GitHubReviewScanner.scan().
        mappings: GITHUB_REVIEW_SKILL_MAPPINGS.

    Returns:
        List of {skill_id, score, evidence} dicts. Only scores > 0 included.
    """
    if metrics is None:
        return []

    metric_values = {
        "lgtm_without_comment": metrics.lgtm_rate,
        "review_comment_depth": metrics.review_comment_depth,
        "ai_coauthor_rate": metrics.ai_coauthor_rate,
        "ai_agent_coauthor_rate": metrics.ai_agent_coauthor_rate,
        "self_review_rate": metrics.self_review_rate,
    }

    per_repo = getattr(metrics, "per_repo", None)

    signals: list[dict] = []
    for metric_key, skill_maps in mappings.items():
        value = metric_values.get(metric_key)
        if value is None:
            continue
        for m in skill_maps:
            score = m["score_fn"](value)
            if score <= 0:
                continue
            evidence = metrics.evidence.get(metric_key, "detected")
            ctx = _rate_context(evidence)
            if per_repo:
                ctx["per_repo"] = per_repo
            signals.append(
                {
                    "skill_id": m["skill_id"],
                    "score": score,
                    "evidence": evidence,
                    "scoring_context": ctx,
                }
            )

    return signals
