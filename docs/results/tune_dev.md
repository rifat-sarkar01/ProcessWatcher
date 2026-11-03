# Threshold calibration — dev

- chosen `tau_review = 0.20` · `tau_flag = 0.90`
- overall P = 0.080 · R = 0.222 · F1 = 0.118
- false flags per compliant clip = 1.00 (limit 0.3; NOT met)
- needs-review rate = 50.0% · timestamp MAE = 0.52 s
- held-out lock: OK (dev only; no held-out tuning)

The false-flag constraint is unreachable on this dev set: late short steps (wipe frame / inspect) are systematically under-detected, so every compliant clip carries a high-confidence `missed` finding. The table above is the best-F1 pair; the run is reported, not silently relaxed.
