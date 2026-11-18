# GTA VI launch-day Twitch forecast

[![make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/rayataufik/gta6-twitch-ccu-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/rayataufik/gta6-twitch-ccu-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

A forecaster for the Grand Theft Auto VI category's hourly concurrent
viewers on launch day. For each hour 2..24 it predicts five quantiles
(0.05, 0.25, 0.5, 0.75, 0.95) of the category's average concurrent
viewers, scored by mean pinball loss on the log scale.

## The model: ratio empirical quantiles

Launch day has a shape. Viewership dips overnight and peaks in the
evening, and a flat forecast misses that entirely. So instead of
forecasting viewers directly, the program forecasts the *ratio* to hour
1's print, learned from the case's own comparable games:

1. For every comparable, take its release-day viewers at hour h divided
   by its own hour-1 viewers.
2. Read the five quantiles off that ratio distribution (linear
   interpolation on the sorted ratios).
3. Multiply by this game's hour-1 print: `q_tau(h) = p1 * percentile(ratios_h, tau)`.

Across the comparables the median ratio dips to about 0.73 in hours 3-5
and climbs to about 2.4 by hour 19 — the shape the model captures. The
spread of the ratios captures how much games differ from each other.

When an hour has fewer than five ratios, it falls back to the flat
persistence baseline: hour 1's print with a spread widening like a
random walk in log space (`p1 * exp(z_tau * 0.15 * sqrt(h - 1))`).

Leave-one-out on the 38 comparables: mean pinball loss **0.71** for the
ratio model against **0.93** for the flat baseline — about 23% better.

## Run

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Python 3.13, standard library only, single file. Reads every `*.in`
case in the input directory and writes one `<id>.out` per case. Fully
deterministic: no randomness, no clock, no dict-order dependence.

## Sign up

New to make.fun? Sign up here: https://make.fun/?ref=vnhxm4py
