# Second-disturbance diagnostic (exploration, not a frozen gate)

Generated 2026-11-02T00:39:24. actuator_lag at 60 s, second disturbance at 180 s (seeded default magnitude), scored 210–420 s on true level. Exploration scenario seeds 101–105 (hidden seeds untouched). Runs: 9 promoted repairs under actuator_lag, Praxion controllers run in the `docker` sandbox. Peak = max |level − target| after the second change; recovery = first time |level − target| ≤ 0.025 held 10 s.

| second disturbance | controller | median MAE | median in-band | median peak | median recovery s | recovered | hard ticks | overrides | episodes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| none | praxion_v2 | 0.0782 | 0.374 | 0.155 | 0.0 | 0.64 | 19 | 84 | 45 |
| none | relay_pi_retuned | 0.0099 | 1.000 | 0.014 | 0.0 | 1.00 | 0 | 0 | 45 |
| none | relay_pi_nominal | 0.2587 | 0.104 | 0.525 | 0.0 | 0.13 | 297 | 501 | 45 |
| none | slow_pid | 0.0159 | 1.000 | 0.040 | 0.0 | 1.00 | 0 | 0 | 45 |
| none | fixed_pid | 0.2585 | 0.101 | 0.525 | — | 0.00 | 327 | 511 | 45 |
| pump_derate | praxion_v2 | 0.0816 | 0.367 | 0.226 | 98.9 | 0.58 | 3 | 21 | 45 |
| pump_derate | relay_pi_retuned | 0.1611 | 0.000 | 0.201 | — | 0.00 | 0 | 0 | 45 |
| pump_derate | relay_pi_nominal | 0.2347 | 0.113 | 0.526 | — | 0.00 | 51 | 144 | 45 |
| pump_derate | slow_pid | 0.0674 | 0.333 | 0.174 | 149.4 | 0.58 | 0 | 0 | 45 |
| pump_derate | fixed_pid | 0.2396 | 0.112 | 0.529 | — | 0.00 | 52 | 126 | 45 |
| extra_leak | praxion_v2 | 0.1009 | 0.229 | 0.382 | 77.4 | 0.56 | 8 | 281 | 45 |
| extra_leak | relay_pi_retuned | 0.1010 | 0.000 | 0.140 | 0.0 | 0.04 | 0 | 0 | 45 |
| extra_leak | relay_pi_nominal | 0.2815 | 0.098 | 0.600 | 15.3 | 0.04 | 203 | 371 | 45 |
| extra_leak | slow_pid | 0.0984 | 0.227 | 0.222 | 28.9 | 0.09 | 18 | 34 | 45 |
| extra_leak | fixed_pid | 0.2844 | 0.095 | 0.599 | — | 0.00 | 191 | 375 | 45 |
| drain_shift | praxion_v2 | 0.0883 | 0.319 | 0.246 | 98.7 | 0.47 | 3 | 21 | 45 |
| drain_shift | relay_pi_retuned | 0.1595 | 0.000 | 0.214 | — | 0.00 | 0 | 0 | 45 |
| drain_shift | relay_pi_nominal | 0.2722 | 0.099 | 0.592 | — | 0.00 | 103 | 244 | 45 |
| drain_shift | slow_pid | 0.1046 | 0.212 | 0.203 | 196.5 | 0.13 | 12 | 20 | 45 |
| drain_shift | fixed_pid | 0.2794 | 0.100 | 0.593 | — | 0.00 | 114 | 265 | 45 |

Episode-level lower MAE under a second disturbance: Praxion v2 78 / relay re-tuned 57 of 135 episodes.

## Per run (median over scenarios)

| run | plant seed | second | Praxion v2 MAE | relay re-tuned MAE | Praxion recovery s | relay recovery s | Praxion peak | relay peak |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| `spark4-20261031-011710-0c4353` | 7 | none | 0.0063 | 0.0099 | 0.0 | 0.0 | 0.016 | 0.015 |
| `spark4-20261031-011710-0c4353` | 7 | pump_derate | 0.0857 | 0.1583 | 166.3 | — | 0.200 | 0.195 |
| `spark4-20261031-011710-0c4353` | 7 | extra_leak | 0.0438 | 0.0929 | 116.6 | — | 0.151 | 0.132 |
| `spark4-20261031-011710-0c4353` | 7 | drain_shift | 0.0729 | 0.1495 | 163.3 | — | 0.219 | 0.202 |
| `spark5-20261031-011712-e34d36` | 11 | none | 0.2113 | 0.0080 | — | 0.0 | 0.543 | 0.012 |
| `spark5-20261031-011712-e34d36` | 11 | pump_derate | 0.0682 | 0.1722 | 97.3 | — | 0.547 | 0.207 |
| `spark5-20261031-011712-e34d36` | 11 | extra_leak | 0.1576 | 0.1032 | 101.3 | — | 0.600 | 0.141 |
| `spark5-20261031-011712-e34d36` | 11 | drain_shift | 0.0490 | 0.1617 | 87.4 | — | 0.600 | 0.211 |
| `spark7-20261031-012959-a9c6d6` | 14 | none | 0.2594 | 0.0127 | — | 0.0 | 0.532 | 0.018 |
| `spark7-20261031-012959-a9c6d6` | 14 | pump_derate | 0.1938 | 0.1611 | — | — | 0.539 | 0.195 |
| `spark7-20261031-012959-a9c6d6` | 14 | extra_leak | 0.2637 | 0.0978 | — | 0.0 | 0.594 | 0.135 |
| `spark7-20261031-012959-a9c6d6` | 14 | drain_shift | 0.2348 | 0.1568 | — | — | 0.590 | 0.206 |
| `spark8-20261031-013049-bc09a1` | 18 | none | 0.0029 | 0.0078 | 0.0 | 0.0 | 0.015 | 0.012 |
| `spark8-20261031-013049-bc09a1` | 18 | pump_derate | 0.0455 | 0.1660 | 103.6 | — | 0.199 | 0.203 |
| `spark8-20261031-013049-bc09a1` | 18 | extra_leak | 0.0283 | 0.1030 | 76.3 | — | 0.147 | 0.145 |
| `spark8-20261031-013049-bc09a1` | 18 | drain_shift | 0.0423 | 0.1613 | 88.0 | — | 0.224 | 0.216 |
| `v13-s11-20261031-020922-a0e68e` | 11 | none | 0.0163 | 0.0080 | 6.6 | 0.0 | 0.031 | 0.012 |
| `v13-s11-20261031-020922-a0e68e` | 11 | pump_derate | 0.2127 | 0.1722 | — | — | 0.221 | 0.207 |
| `v13-s11-20261031-020922-a0e68e` | 11 | extra_leak | 0.0752 | 0.1032 | 106.3 | — | 0.185 | 0.141 |
| `v13-s11-20261031-020922-a0e68e` | 11 | drain_shift | 0.2048 | 0.1617 | — | — | 0.214 | 0.211 |
| `v13-s14-20261031-015222-af63b9` | 14 | none | 0.0046 | 0.0127 | 0.0 | 0.0 | 0.011 | 0.018 |
| `v13-s14-20261031-015222-af63b9` | 14 | pump_derate | 0.0443 | 0.1611 | 86.0 | — | 0.193 | 0.195 |
| `v13-s14-20261031-015222-af63b9` | 14 | extra_leak | 0.0324 | 0.0978 | 70.7 | 0.0 | 0.140 | 0.135 |
| `v13-s14-20261031-015222-af63b9` | 14 | drain_shift | 0.0547 | 0.1568 | 151.0 | — | 0.212 | 0.206 |
| `v13-s18-20261031-021658-2cc943` | 18 | none | 0.0765 | 0.0078 | 0.0 | 0.0 | 0.147 | 0.012 |
| `v13-s18-20261031-021658-2cc943` | 18 | pump_derate | 0.0763 | 0.1660 | 61.5 | — | 0.213 | 0.203 |
| `v13-s18-20261031-021658-2cc943` | 18 | extra_leak | 0.1284 | 0.1030 | — | — | 0.314 | 0.145 |
| `v13-s18-20261031-021658-2cc943` | 18 | drain_shift | 0.0938 | 0.1613 | — | — | 0.246 | 0.216 |
| `v13-s3-20261031-015222-39a872` | 3 | none | 0.2544 | 0.0102 | — | 0.0 | 0.534 | 0.015 |
| `v13-s3-20261031-015222-39a872` | 3 | pump_derate | 0.0684 | 0.1659 | 89.1 | — | 0.514 | 0.201 |
| `v13-s3-20261031-015222-39a872` | 3 | extra_leak | 0.2768 | 0.1028 | — | — | 0.600 | 0.143 |
| `v13-s3-20261031-015222-39a872` | 3 | drain_shift | 0.1929 | 0.1620 | 104.5 | — | 0.549 | 0.214 |
| `v13-s7-20261031-020602-18f408` | 7 | none | 0.1116 | 0.0099 | 51.3 | 0.0 | 0.406 | 0.015 |
| `v13-s7-20261031-020602-18f408` | 7 | pump_derate | 0.2209 | 0.1583 | 145.2 | — | 0.336 | 0.195 |
| `v13-s7-20261031-020602-18f408` | 7 | extra_leak | 0.1642 | 0.0929 | 95.8 | — | 0.508 | 0.132 |
| `v13-s7-20261031-020602-18f408` | 7 | drain_shift | 0.2263 | 0.1495 | — | — | 0.302 | 0.202 |
