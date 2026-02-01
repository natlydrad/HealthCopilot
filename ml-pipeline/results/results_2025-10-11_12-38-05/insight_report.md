# 🧠 HealthCopilot Insight Report

Source folder: `results_2025-10-11_12-38-05`


## 📊 Model Predictability

| Rank | Target | R² | adjR² | AIC |
|------|---------|----|--------|------|
| 1 | rem_min | 0.136 | 0.126 | 1785.1 |
| 2 | steps_sum | 0.094 | 0.089 | 3651.4 |
| 3 | core_min | 0.030 | 0.025 | 2114.5 |
| 4 | total_min | 0.030 | 0.002 | 2175.0 |
| 5 | deep_min | 0.011 | -0.012 | 1639.1 |
| 6 | basal_kcal | 0.015 | -0.012 | 2284.8 |
| 7 | glucose_mean | 0.040 | -0.018 | 629.9 |
| 8 | active_kcal | 0.010 | -0.018 | 2291.9 |
| 9 | energy_score | 0.006 | -0.022 | 2477.9 |
| 10 | resting_hr_bpm | 0.005 | -0.022 | 1391.6 |
| 11 | hrv_sdnn_ms | 0.001 | -0.027 | 1774.7 |

**Mean R²:** 0.034 **Median R²:** 0.015


## 🔍 Top Model Insights


### 🎯 rem_min (adjR²=0.126)
- ↑ **deep_min_lag1** → rem_min (+0.502, q=0.000) ⭐


### 🎯 steps_sum (adjR²=0.089)
- ↑ **vo2max_ml_kg_min_lag3** → steps_sum (+113.230, q=0.000) ⭐


### 🎯 core_min (adjR²=0.025)
- ↑ **vo2max_ml_kg_min_lag2** → core_min (+0.945, q=0.016) ⭐


### 🎯 total_min (adjR²=0.002)
_No significant predictors found._


### 🎯 deep_min (adjR²=-0.012)
_No significant predictors found._


### 🎯 basal_kcal (adjR²=-0.012)
_No significant predictors found._


### 🎯 glucose_mean (adjR²=-0.018)
_No significant predictors found._


### 🎯 active_kcal (adjR²=-0.018)
_No significant predictors found._


### 🎯 energy_score (adjR²=-0.022)
_No significant predictors found._


### 🎯 resting_hr_bpm (adjR²=-0.022)
_No significant predictors found._


## 🔗 Network-Like Correlations


### steps_sum
- Negative: **rem_min_lag1_lag2_lag3_3d_ma_7d_ma** (r=-0.21, q=0.021)
- Negative: **active_kcal_lag1_3d_ma** (r=+0.21, q=0.026)
- Negative: **active_kcal_7d_ma** (r=+0.28, q=0.001)

### glucose_mean
- Positive: **hrv_sdnn_ms_lag1_lag2_lag3_3d_ma_7d_ma** (r=+0.60, q=0.000)
- Positive: **hrv_sdnn_ms_lag2_lag3_3d_ma_7d_ma** (r=+0.58, q=0.000)
- Positive: **hrv_sdnn_ms_lag1_lag2_lag3_7d_ma** (r=+0.58, q=0.000)
- Negative: **vo2max_ml_kg_min_lag1_lag3_3d_ma_7d_ma** (r=-0.43, q=0.000)
- Negative: **vo2max_ml_kg_min_lag1_lag3_7d_ma** (r=-0.43, q=0.000)
- Negative: **vo2max_ml_kg_min_lag1_lag2_3d_ma_7d_ma** (r=-0.43, q=0.000)

### active_kcal
- Positive: **energy_score** (r=+0.84, q=0.000)
- Positive: **steps_sum** (r=+0.50, q=0.000)
- Positive: **basal_kcal** (r=+0.39, q=0.000)
- Negative: **vo2max_ml_kg_min** (r=+0.27, q=0.008)
- Negative: **steps_sum_3d_ma** (r=+0.28, q=0.005)
- Negative: **basal_kcal** (r=+0.39, q=0.000)

### basal_kcal
- Positive: **energy_score** (r=+0.83, q=0.000)
- Positive: **active_kcal** (r=+0.39, q=0.000)
- Positive: **resting_hr_bpm** (r=+0.35, q=0.000)
- Negative: **vo2max_ml_kg_min_3d_ma** (r=-0.29, q=0.006)
- Negative: **steps_sum_lag3_7d_ma** (r=-0.27, q=0.006)
- Negative: **steps_sum_lag1_lag2_7d_ma** (r=-0.27, q=0.006)

### hrv_sdnn_ms
- Negative: **resting_hr_bpm** (r=-0.32, q=0.000)
- Negative: **resting_hr_bpm_3d_ma** (r=-0.31, q=0.001)
- Negative: **resting_hr_bpm_7d_ma** (r=-0.27, q=0.004)

### vo2max_ml_kg_min
- Positive: **steps_sum** (r=+0.46, q=0.000)
- Negative: **basal_kcal_3d_ma** (r=-0.23, q=0.011)
- Negative: **basal_kcal_lag1_lag2_lag3_3d_ma_7d_ma** (r=-0.22, q=0.017)
- Negative: **rem_min_lag2_3d_ma** (r=-0.22, q=0.017)

### total_min
- Positive: **core_min** (r=+0.58, q=0.000)
- Positive: **rem_min** (r=+0.48, q=0.000)
- Positive: **core_min_3d_ma** (r=+0.37, q=0.000)
- Negative: **core_min_lag1_3d_ma_7d_ma** (r=+0.20, q=0.062)
- Negative: **core_min_lag1_lag2_7d_ma** (r=+0.21, q=0.054)
- Negative: **core_min_lag3_7d_ma** (r=+0.21, q=0.054)

### core_min
- Positive: **rem_min** (r=+0.75, q=0.000)
- Positive: **total_min** (r=+0.58, q=0.000)
- Positive: **total_min_3d_ma** (r=+0.51, q=0.000)
- Negative: **total_min_lag2_3d_ma** (r=+0.24, q=0.014)

### rem_min
- Positive: **core_min** (r=+0.75, q=0.000)
- Positive: **core_min_3d_ma** (r=+0.53, q=0.000)
- Positive: **total_min** (r=+0.48, q=0.000)
- Negative: **hrv_sdnn_ms_lag2_3d_ma_7d_ma** (r=+0.20, q=0.061)
- Negative: **hrv_sdnn_ms_lag3_7d_ma** (r=+0.21, q=0.059)
- Negative: **hrv_sdnn_ms_lag1_lag2_7d_ma** (r=+0.21, q=0.059)

### steps_sum_lag1
- Positive: **steps_sum_3d_ma** (r=+0.84, q=0.000)
- Positive: **steps_sum_7d_ma** (r=+0.75, q=0.000)
- Positive: **steps_sum_3d_ma_7d_ma** (r=+0.69, q=0.000)
- Negative: **rem_min_lag2_3d_ma** (r=-0.20, q=0.033)
- Negative: **active_kcal_lag2_3d_ma** (r=+0.21, q=0.017)
- Negative: **active_kcal_3d_ma_7d_ma** (r=+0.25, q=0.003)