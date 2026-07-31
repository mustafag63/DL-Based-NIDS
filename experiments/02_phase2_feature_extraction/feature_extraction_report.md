# Phase 2 - Feature Extraction Report


All 8 windows (window_01-08) included. window_01_0pct was re-captured after a Zeek restart bug was found and fixed; the old broken capture is archived separately and never enters this pipeline.


## Filtering counts per window


| window | raw conn.log | after lab-IP filter | attack flows | benign flows | raw dns.log | dns.log techmarket.lab | raw attack_log.csv | attack_log.csv in window |
|---|---|---|---|---|---|---|---|---|
| window_01_0pct | 559 | 547 | 0 | 547 | 37 | 15 | 125 | 0 |
| window_02_3pct | 4127 | 4104 | 126 | 3978 | 148 | 116 | 134 | 6 |
| window_03_5pct | 4257 | 4180 | 214 | 3966 | 203 | 121 | 143 | 6 |
| window_04_7pct | 4800 | 4777 | 304 | 4473 | 161 | 129 | 152 | 6 |
| window_05_12pct | 4967 | 4941 | 550 | 4391 | 167 | 135 | 161 | 6 |
| window_06_15pct | 5749 | 5719 | 712 | 5007 | 187 | 143 | 170 | 6 |
| window_07_17pct | 6151 | 6116 | 826 | 5290 | 188 | 148 | 179 | 6 |
| window_08_22pct | 6544 | 6321 | 1138 | 5183 | 366 | 154 | 188 | 6 |

## Flow-attack ratio vs actual_attack_pct (validation)

| window_id       |   flow_attack_pct |   actual_attack_pct |   n_flows |
|:----------------|------------------:|--------------------:|----------:|
| window_01_0pct  |           0       |             0       |       547 |
| window_02_3pct  |           3.07018 |             3.0773  |      4104 |
| window_03_5pct  |           5.11962 |             5.61428 |      4180 |
| window_04_7pct  |           6.36383 |             6.375   |      4777 |
| window_05_12pct |          11.1313  |            11.1133  |      4941 |
| window_06_15pct |          12.4497  |            12.4196  |      5719 |
| window_07_17pct |          13.5056  |            13.4612  |      6116 |
| window_08_22pct |          18.0035  |            18.75    |      6321 |


## Final feature matrix

Shape: (36705, 22)

Saved files:
- `/Users/mustafa/Desktop/NIDS/data/ids-dataset-features/features_all_windows.csv`
- `/Users/mustafa/Desktop/NIDS/data/ids-dataset-features/features_all_windows.parquet`


## Features used

Numeric (StandardScaler, **fit only on the train split - leakage-free**, transform applied to all rows): ['duration', 'orig_bytes', 'resp_bytes', 'orig_pkts', 'resp_pkts', 'bytes_per_sec', 'pkts_per_sec', 'byte_ratio']

Categorical (OneHotEncoder, global fit): ['proto', 'service', 'conn_state']

`missed_bytes` dropped: constant 0 across all 8 windows (zero variance, no signal).

`orig_ip_bytes`/`resp_ip_bytes` dropped: r=0.996/0.99996 with orig_bytes/resp_bytes.

`bytes_per_sec`, `pkts_per_sec`: set to 0 for flows with duration==0 (mostly S0/OTH, never-established connections, 0 rows total) - no division by zero.

`byte_ratio` = orig_bytes/(resp_bytes+1): expected to help distinguish Slowloris-style 'send little data, keep the connection open' attacks.

Train/val/test split done with signature-based GroupShuffleSplit (official seed=1), see the `03_phase3_splits/` folder.


## bytes_per_sec / pkts_per_sec / byte_ratio: benign vs attack (raw, unscaled)

|   is_attack |   ('bytes_per_sec', 'mean') |   ('bytes_per_sec', 'std') |   ('bytes_per_sec', 'median') |   ('pkts_per_sec', 'mean') |   ('pkts_per_sec', 'std') |   ('pkts_per_sec', 'median') |   ('byte_ratio', 'mean') |   ('byte_ratio', 'std') |   ('byte_ratio', 'median') |
|------------:|----------------------------:|---------------------------:|------------------------------:|---------------------------:|--------------------------:|-----------------------------:|-------------------------:|------------------------:|---------------------------:|
|           0 |                    16242.4  |                   67435.9  |                      59.9583  |                     470.92 |                    2074.2 |                      1.42699 |                0.0805688 |                0.131609 |                  0.0604513 |
|           1 |                     1131.61 |                    2474.01 |                       7.16235 |                   54359.5  |                   84921.9 |                    112.962   |               70.2477    |               99.106    |                  0.0322581 |