# 🧪 N-of-1 Experiment Plan

_Generated from `results_2025-10-11_12-38-05`_


## rem_min (adjR²=0.126)
- **Goal metric:** daily `rem_min`
- **Design:** 14 days → **7-day baseline** (no change), then **7-day intervention**
- **Tracking:** 7-day rolling mean, day-to-day deltas, annotate weekends
- **Success:** Baseline vs intervention mean improves in desired direction; sanity-check with a simple OLS on days 1..14 with an intervention dummy.

- **Intervention:** increase **deep min lag1 (lag 1d)** by **~30 min/day** (expect effect after ~1 day) (model coef +0.502, q=0.000) ⭐

**Confounders to log:** illness, travel, caffeine, alcohol, unusually hard workouts, late meals, menstrual cycle phase.
