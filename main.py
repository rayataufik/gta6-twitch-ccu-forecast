"""Forecast GTA VI's launch-day Twitch viewers hour by hour.

Model: ratio empirical quantiles. For each forecast hour h = 2..24, look at
every comparable game in the case, take its release-day viewers at hour h
divided by its own hour-1 viewers, and read the five scored quantiles off
that ratio distribution. The forecast is hour 1's print times each ratio
quantile:

    q_tau(h) = p1 * percentile(ratios_h, tau),  tau in [0.05, 0.25, 0.5, 0.75, 0.95]

A comparable's release-day hours are the 24 hourly points starting at its
day_start. A comparable counts for an hour only if it has a positive print
at both hour 1 and that hour. When fewer than five ratios are available for
an hour, the hour falls back to the flat persistence baseline (hour 1's
print with a spread that widens like a random walk in log space).

Why ratios, not a flat forecast: launch-day viewership has a real shape.
Across the comparables the median ratio dips to about 0.73 in hours 3-5
(the overnight lull) and climbs to about 2.4 by hour 19 (the evening
peak). A flat forecast misses that shape entirely; the ratio quantiles
capture it, and the spread of the ratios captures how much games differ.

Deterministic: no randomness, no clock, no dict-order dependence. Inputs
are read in name order, comparables are sorted by name, and every hour's
ratios are sorted before the percentile is taken.

Run:  mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
from datetime import datetime
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level, used by the fallback.
Z = [-1.645, -0.674, 0, 0.674, 1.645]
# The fallback spread, in natural-log units per square-root hour.
SIGMA = 0.15
# An hour needs at least this many ratios before the empirical quantiles
# are trusted; fewer, and the flat baseline is the safer forecast.
MIN_RATIOS = 5


def round2(x):
    """x rounded to 2 decimals, half up, as JavaScript's Math.round does it.

    A whole number comes back as an int, so json.dumps writes 1240 where
    JavaScript writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def parse_time(text):
    """An ISO-8601 timestamp with a Z suffix, as a timezone-aware datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def release_day_hours(comp):
    """A comparable's release-day viewers, keyed by hour 1..24.

    The 24 hourly points starting at the comparable's day_start. Points
    outside that window (pre-release history, later days) are ignored, as
    are non-positive prints.
    """
    start = parse_time(comp["day_start"])
    hours = {}
    for point in comp.get("hourly", []):
        viewers = point.get("viewers")
        if not isinstance(viewers, (int, float)) or viewers <= 0:
            continue
        delta = (parse_time(point["from"]) - start).total_seconds()
        hour = int(delta // 3600) + 1
        if 1 <= hour <= 24:
            hours[hour] = viewers
    return hours


def percentile(sorted_values, tau):
    """The tau-quantile of a sorted list, by linear interpolation.

    The position is (n - 1) * tau, interpolated between the two nearest
    sorted values; tau = 0 gives the minimum, tau = 1 the maximum.
    """
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    position = (n - 1) * tau
    low = int(position)
    fraction = position - low
    if low + 1 >= n:
        return sorted_values[-1]
    return sorted_values[low] * (1 - fraction) + sorted_values[low + 1] * fraction


def clean_quantiles(qs):
    """Enforce the output contract on one hour's five quantiles.

    Every value must be finite, above 0 and at most 1e9, and the row must
    be non-decreasing. The ratio quantiles already satisfy this by
    construction (percentiles of sorted ratios, rounded monotonically), and
    so does the fallback, but a defensive pass means a malformed case can
    never produce an invalid row: clamp each value into (0, 1e9], then run
    a running maximum so the row can only step up.
    """
    cleaned = []
    floor = 0.0
    for value in qs:
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            value = 1.0
        if value > 1e9:
            value = 1e9
        value = max(value, floor)
        floor = value
        cleaned.append(round2(value))
    return cleaned


def baseline_quantiles(p1, h):
    """The flat persistence forecast for hour h, as a fallback."""
    return clean_quantiles(
        [p1 * math.exp(z * SIGMA * math.sqrt(h - 1)) for z in Z]
    )


def hour_quantiles(p1, ratios, h):
    """The five forecast quantiles for one hour from its ratio list."""
    if len(ratios) < MIN_RATIOS:
        return baseline_quantiles(p1, h)
    ordered = sorted(ratios)
    return clean_quantiles([p1 * percentile(ordered, tau) for tau in LEVELS])


def forecast_case(case, name):
    """Forecast one case: 23 rows, hours 2..24, five quantiles each."""
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])

    ratios_by_hour = {h: [] for h in range(2, 25)}
    for comp in sorted(case.get("comparables", []), key=lambda c: c.get("name", "")):
        hours = release_day_hours(comp)
        v1 = hours.get(1)
        if v1 is None:
            continue
        for h in range(2, 25):
            vh = hours.get(h)
            if vh is not None:
                ratios_by_hour[h].append(vh / v1)

    rows = []
    for row in sorted(case["forecast"], key=lambda r: r["hour"]):
        h = row["hour"]
        rows.append({"hour": h, "q": hour_quantiles(p1, ratios_by_hour[h], h)})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
