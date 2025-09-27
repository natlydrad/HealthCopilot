# HealthCopilot Model Report

## Summary Table

| Target | Metrics | SHAP Summary | SHAP Waterfall |
|--------|---------|--------------|----------------|
| aucGlucose | MAE=166.19, R2=0.99 | ![summary](shap_summary_aucGlucose.png) | ![waterfall](shap_waterfall_aucGlucose_0.png) |
| deltaGlucose | MAE=0.91, R2=1.00 | ![summary](shap_summary_deltaGlucose.png) | ![waterfall](shap_waterfall_deltaGlucose_0.png) |
| spike | ACC=1.000, F1=1.000 | ![summary](shap_summary_spike.png) | ![waterfall](shap_waterfall_spike_0.png) |
| timeToPeak | MAE=2.49, R2=0.99 | ![summary](shap_summary_timeToPeak.png) | ![waterfall](shap_waterfall_timeToPeak_0.png) |
| durationAboveBaseline | MAE=1.82, R2=1.00 | ![summary](shap_summary_durationAboveBaseline.png) | ![waterfall](shap_waterfall_durationAboveBaseline_0.png) |
| timeToReturnBaseline | MAE=0.18, R2=1.00 | ![summary](shap_summary_timeToReturnBaseline.png) | ![waterfall](shap_waterfall_timeToReturnBaseline_0.png) |
| numFluctuations | MAE=0.21, R2=1.00 | ![summary](shap_summary_numFluctuations.png) | ![waterfall](shap_waterfall_numFluctuations_0.png) |
