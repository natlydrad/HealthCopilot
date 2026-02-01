<<<<<<< HEAD
# 🧪 N-of-1 Experiment Plan

_Generated from `results_2025-10-11_12-38-05`_


## rem_min (adjR²=0.126)
- **Goal metric:** daily `rem_min`
- **Design:** 14 days → **7-day baseline** (no change), then **7-day intervention**
- **Tracking:** 7-day rolling mean, day-to-day deltas, annotate weekends
- **Success:** Baseline vs intervention mean improves in desired direction; sanity-check with a simple OLS on days 1..14 with an intervention dummy.

- **Intervention:** increase **deep min lag1 (lag 1d)** by **~30 min/day** (expect effect after ~1 day) (model coef +0.502, q=0.000) ⭐

**Confounders to log:** illness, travel, caffeine, alcohol, unusually hard workouts, late meals, menstrual cycle phase.
=======
# 🧪 Experiments To Run (with scientific justification)


## Goal: ↑ rem min

### Experiment 1 — daily steps (↑)
**Why this?** Strong association with rem min (r=0.3, q=0.01).

**How to run it:**
- **Design:** stepped dose across **4 weeks** (1wk, 1wk, 1wk, 1wk).
- **Step plan:** 0, 2000, 3000, maintain.
- **Adherence:** Daily steps must exceed baseline by the step goal (+2k or +3k).
- **Instructions:** Week1 baseline; Week2 +2k/day; Week3 +3k/day; Week4 maintain.
- **Expected direction:** increase **daily steps** → higher **rem min**.

**Design justification (real-science vibe):**
- **Onset & carryover:** Behavior changes/fitness adaptation need gradual dosing; segmented regression captures level/slope.
- **Replication & bias control:** design provides repeated contrasts within you; randomization/blocks reduce weekday trends; HAC/ITS handle autocorrelation.
- **Minimum duration:** aim for ≥20–30 observation days overall to detect moderate effects.

**What your data so far says (informal):**
- Diff-in-means (HAC): effect -4.202 (p=0.517, n=178)
- ITS: level -26.360 (p=0.103), slope +2.745 (p=0.521), adjR²=0.010.
>>>>>>> ebf6a02
