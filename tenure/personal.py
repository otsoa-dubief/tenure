"""Personal benchmark: each model's verified record per action type, on the user's own work.

Pure functions plus reads only: nothing here writes to the store.
"""
import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k faults out of n checks. With n == 0 it is (0.0, 1.0)."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def split_agent(agent: str) -> tuple[str, str]:
    """`model@provider`: the model is everything before the LAST "@", the provider everything after."""
    model, sep, provider = agent.rpartition("@")
    if not sep:
        return agent, "unknown"
    return model, provider or "unknown"


def model_table(store, type_key: str | None = None, min_n: int = 20) -> list[dict]:
    """One row per (agent, type): agent, model, provider, type, successes, faults, sessions_in_series,
    rate, low, high, enough.

    `rate` is faults / (successes + faults), None when there is no check. `low`/`high` is the Wilson interval
    of that rate. `sessions_in_series` is the number of distinct sessions in the CURRENT series (at most 10),
    not a lifetime count: the store keeps none. `enough` means at least `min_n` checks.
    Sorted by type, then upper bound ascending (most reliable first), then agent.
    """
    rows = []
    for agent, s in store.states():
        if type_key is not None and s.key != type_key:
            continue
        model, provider = split_agent(agent)
        n = s.successes + s.faults
        low, high = wilson(s.faults, n)
        rows.append({
            "agent": agent, "model": model, "provider": provider, "type": s.key,
            "successes": s.successes, "faults": s.faults, "sessions_in_series": len(s.sessions),
            "rate": (s.faults / n) if n else None, "low": low, "high": high,
            "enough": n > 0 and n >= min_n,
        })
    rows.sort(key=lambda r: (r["type"], r["high"], r["agent"]))
    return rows
