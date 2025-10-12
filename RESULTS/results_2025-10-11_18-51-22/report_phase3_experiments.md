# 📊 Phase 3 → N-of-1 Summary

- **Days analyzed:** 184
- **Features:** 363
- **Targets modeled:** 11

We ran:
1. Descriptive correlations (Pearson r + FDR)
2. OLS + HAC regressions per target
3. Behavioral-lever filter → N-of-1 experiments

---
## 🔗 Strongest correlations

- **steps_sum** ↔ **steps_sum_3d_ma** (r = +0.83, q = 0.000)
- **steps_sum** ↔ **steps_sum_7d_ma** (r = +0.72, q = 0.000)
- **glucose_mean** ↔ **glucose_mean_3d_ma** (r = +0.88, q = 0.000)
- **glucose_mean** ↔ **glucose_mean_7d_ma** (r = +0.72, q = 0.000)
- **glucose_mean** ↔ **vo2max_ml_kg_min_lag1_lag3_3d_ma_7d_ma** (r = -0.43, q = 0.000)
- **glucose_mean** ↔ **vo2max_ml_kg_min_lag1_lag3_7d_ma** (r = -0.43, q = 0.000)
- **active_kcal** ↔ **energy_score** (r = +0.84, q = 0.000)
- **active_kcal** ↔ **active_kcal_3d_ma** (r = +0.68, q = 0.000)
- **basal_kcal** ↔ **energy_score** (r = +0.83, q = 0.000)
- **basal_kcal** ↔ **basal_kcal_3d_ma** (r = +0.40, q = 0.000)
- **basal_kcal** ↔ **vo2max_ml_kg_min_3d_ma** (r = -0.29, q = 0.006)
- **basal_kcal** ↔ **steps_sum_lag1_lag2_7d_ma** (r = -0.27, q = 0.006)
- **resting_hr_bpm** ↔ **resting_hr_bpm_3d_ma** (r = +0.55, q = 0.000)
- **resting_hr_bpm** ↔ **basal_kcal** (r = +0.35, q = 0.000)
- **resting_hr_bpm** ↔ **hrv_sdnn_ms** (r = -0.32, q = 0.001)

---
## 📈 Model performance

1. **rem_min** — adj R² = 0.126
2. **steps_sum** — adj R² = 0.089
3. **core_min** — adj R² = 0.025
4. **total_min** — adj R² = 0.002
5. **deep_min** — adj R² = -0.012
6. **basal_kcal** — adj R² = -0.012
7. **glucose_mean** — adj R² = -0.018
8. **active_kcal** — adj R² = -0.018

---
## 🧪 Experiments you can actually run
