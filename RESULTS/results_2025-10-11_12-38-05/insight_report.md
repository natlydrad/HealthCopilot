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
- ↑ **core_min_lag1** → rem_min (+0.057, q=0.103) 


### 🎯 steps_sum (adjR²=0.089)
- ↑ **vo2max_ml_kg_min_lag3** → steps_sum (+113.230, q=0.000) ⭐


### 🎯 core_min (adjR²=0.025)
- ↑ **vo2max_ml_kg_min_lag2** → core_min (+0.945, q=0.016) ⭐


### 🎯 total_min (adjR²=0.002)
- ↓ **resting_hr_bpm_lag3** → total_min (-0.996, q=0.256) 
- ↑ **steps_sum_lag3** → total_min (+0.002, q=0.256) 
- ↓ **rem_min_lag3** → total_min (-0.227, q=0.417) 
- ↑ **deep_min_lag3** → total_min (+0.167, q=0.812) 
- ↓ **vo2max_ml_kg_min_lag3** → total_min (-0.074, q=0.895) 


### 🎯 deep_min (adjR²=-0.012)
- ↑ **steps_sum_lag3** → deep_min (+0.000, q=0.711) 
- ↓ **vo2max_ml_kg_min_lag3** → deep_min (-0.115, q=0.711) 
- ↓ **rem_min_lag3** → deep_min (-0.026, q=0.725) 
- ↑ **resting_hr_bpm_lag3** → deep_min (+0.004, q=0.990) 


### 🎯 basal_kcal (adjR²=-0.012)
- ↓ **steps_sum_lag3** → basal_kcal (-0.002, q=0.528) 
- ↓ **rem_min_lag3** → basal_kcal (-0.173, q=0.528) 
- ↓ **deep_min_lag3** → basal_kcal (-0.089, q=0.845) 
- ↑ **hrv_sdnn_ms_lag3** → basal_kcal (+0.065, q=0.845) 
- ↓ **vo2max_ml_kg_min_lag3** → basal_kcal (-0.076, q=0.876) 


### 🎯 glucose_mean (adjR²=-0.018)
- ↓ **vo2max_ml_kg_min_lag1** → glucose_mean (-0.066, q=0.538) 
- ↑ **rem_min_lag1** → glucose_mean (+0.020, q=0.538) 
- ↓ **active_kcal_lag1** → glucose_mean (-0.008, q=0.538) 
- ↑ **steps_sum_lag1** → glucose_mean (+0.000, q=0.680) 
- ↓ **deep_min_lag1** → glucose_mean (-0.019, q=0.680) 


### 🎯 active_kcal (adjR²=-0.018)
- ↑ **vo2max_ml_kg_min_lag3** → active_kcal (+0.447, q=0.908) 
- ↓ **rem_min_lag3** → active_kcal (-0.151, q=0.908) 
- ↑ **steps_sum_lag3** → active_kcal (+0.001, q=0.908) 
- ↑ **hrv_sdnn_ms_lag3** → active_kcal (+0.113, q=0.908) 
- ↓ **deep_min_lag3** → active_kcal (-0.044, q=0.908) 


### 🎯 energy_score (adjR²=-0.022)
- ↓ **rem_min_lag3** → energy_score (-0.323, q=0.804) 
- ↓ **steps_sum_lag3** → energy_score (-0.001, q=0.804) 
- ↑ **hrv_sdnn_ms_lag3** → energy_score (+0.179, q=0.804) 
- ↑ **vo2max_ml_kg_min_lag3** → energy_score (+0.370, q=0.804) 
- ↓ **deep_min_lag3** → energy_score (-0.133, q=0.804) 


### 🎯 resting_hr_bpm (adjR²=-0.022)
- ↑ **deep_min_lag3** → resting_hr_bpm (+0.032, q=0.863) 
- ↓ **steps_sum_lag3** → resting_hr_bpm (-0.000, q=0.966) 
- ↑ **vo2max_ml_kg_min_lag3** → resting_hr_bpm (+0.011, q=0.966) 
- ↑ **hrv_sdnn_ms_lag3** → resting_hr_bpm (+0.004, q=0.966) 
- ↓ **rem_min_lag3** → resting_hr_bpm (-0.001, q=0.966) 


## 🔗 Network-Like Correlations


### steps_sum
- Positive: **steps_sum_3d_ma** (r=+0.83, q=0.000)
- Positive: **steps_sum_7d_ma** (r=+0.72, q=0.000)
- Positive: **steps_sum_3d_ma_7d_ma** (r=+0.65, q=0.000)
- Negative: **rem_min_lag1_lag2_lag3_3d_ma_7d_ma** (r=-0.21, q=0.021)
- Negative: **active_kcal_lag1_3d_ma** (r=+0.21, q=0.026)
- Negative: **active_kcal_7d_ma** (r=+0.28, q=0.001)

### glucose_mean
- Positive: **glucose_mean_3d_ma** (r=+0.88, q=0.000)
- Positive: **glucose_mean_7d_ma** (r=+0.72, q=0.000)
- Positive: **glucose_mean_3d_ma_7d_ma** (r=+0.61, q=0.000)
- Negative: **vo2max_ml_kg_min_lag1_lag3_3d_ma_7d_ma** (r=-0.43, q=0.000)
- Negative: **vo2max_ml_kg_min_lag1_lag3_7d_ma** (r=-0.43, q=0.000)
- Negative: **vo2max_ml_kg_min_lag1_lag2_3d_ma_7d_ma** (r=-0.43, q=0.000)

### active_kcal
- Positive: **energy_score** (r=+0.84, q=0.000)
- Positive: **active_kcal_3d_ma** (r=+0.68, q=0.000)
- Positive: **steps_sum** (r=+0.50, q=0.000)
- Negative: **active_kcal_lag1_3d_ma** (r=+0.25, q=0.024)
- Negative: **active_kcal_lag2** (r=+0.25, q=0.021)
- Negative: **vo2max_ml_kg_min** (r=+0.27, q=0.008)

### basal_kcal
- Positive: **energy_score** (r=+0.83, q=0.000)
- Positive: **basal_kcal_3d_ma** (r=+0.40, q=0.000)
- Positive: **active_kcal** (r=+0.39, q=0.000)
- Negative: **vo2max_ml_kg_min_3d_ma** (r=-0.29, q=0.006)
- Negative: **steps_sum_lag3_7d_ma** (r=-0.27, q=0.006)
- Negative: **steps_sum_lag1_lag2_7d_ma** (r=-0.27, q=0.006)

### hrv_sdnn_ms
- Positive: **hrv_sdnn_ms_3d_ma** (r=+0.75, q=0.000)
- Positive: **hrv_sdnn_ms_7d_ma** (r=+0.58, q=0.000)
- Positive: **hrv_sdnn_ms_3d_ma_7d_ma** (r=+0.45, q=0.000)
- Negative: **resting_hr_bpm** (r=-0.32, q=0.000)
- Negative: **resting_hr_bpm_3d_ma** (r=-0.31, q=0.001)
- Negative: **resting_hr_bpm_7d_ma** (r=-0.27, q=0.004)

### vo2max_ml_kg_min
- Positive: **vo2max_ml_kg_min_3d_ma** (r=+0.76, q=0.000)
- Positive: **vo2max_ml_kg_min_7d_ma** (r=+0.64, q=0.000)
- Positive: **vo2max_ml_kg_min_3d_ma_7d_ma** (r=+0.53, q=0.000)
- Negative: **basal_kcal_3d_ma** (r=-0.23, q=0.011)
- Negative: **basal_kcal_lag1_lag2_lag3_3d_ma_7d_ma** (r=-0.22, q=0.017)
- Negative: **rem_min_lag2_3d_ma** (r=-0.22, q=0.017)

### total_min
- Positive: **total_min_3d_ma** (r=+0.66, q=0.000)
- Positive: **core_min** (r=+0.58, q=0.000)
- Positive: **rem_min** (r=+0.48, q=0.000)
- Negative: **core_min_lag1_3d_ma_7d_ma** (r=+0.20, q=0.062)
- Negative: **total_min_lag1_lag2_lag3_3d_ma** (r=+0.21, q=0.056)
- Negative: **core_min_lag1_lag2_7d_ma** (r=+0.21, q=0.054)

### core_min
- Positive: **rem_min** (r=+0.75, q=0.000)
- Positive: **core_min_3d_ma** (r=+0.66, q=0.000)
- Positive: **total_min** (r=+0.58, q=0.000)
- Negative: **core_min_lag3_7d_ma** (r=+0.21, q=0.046)
- Negative: **core_min_lag1_lag2_7d_ma** (r=+0.21, q=0.046)
- Negative: **core_min_lag2_7d_ma** (r=+0.21, q=0.038)

### rem_min
- Positive: **core_min** (r=+0.75, q=0.000)
- Positive: **rem_min_3d_ma** (r=+0.62, q=0.000)
- Positive: **core_min_3d_ma** (r=+0.53, q=0.000)
- Negative: **hrv_sdnn_ms_lag2_3d_ma_7d_ma** (r=+0.20, q=0.061)
- Negative: **hrv_sdnn_ms_lag3_7d_ma** (r=+0.21, q=0.059)
- Negative: **hrv_sdnn_ms_lag1_lag2_7d_ma** (r=+0.21, q=0.059)

### steps_sum_lag1
- Positive: **steps_sum_3d_ma** (r=+0.84, q=0.000)
- Positive: **steps_sum_lag1_3d_ma** (r=+0.84, q=0.000)
- Positive: **steps_sum_7d_ma** (r=+0.75, q=0.000)
- Negative: **rem_min_lag2_3d_ma** (r=-0.20, q=0.033)
- Negative: **active_kcal_lag2_3d_ma** (r=+0.21, q=0.017)
- Negative: **active_kcal_3d_ma_7d_ma** (r=+0.25, q=0.003)