# IndPenSim data dictionary

This dictionary follows [contract v1](data_contract.md) and its [machine-readable schemas](../config/indpensim_contract.json). It describes the selected original release, not newly generated simulator runs. The [verification report](data_verification.md) records access failures and primary-source evidence. No contract changes are proposed here.

## Evidence and interpretation

- **Documented:** meaning in an original CSV header, the publisher release, or author paper. A reported unit is a published label, not an independently verified calibration.
- **Observed:** facts from the complete original-data inspection, retained in [inspection.json](evidence/indpensim/inspection.json).
- **Unknown:** absent documentation or inconsistent scale. These gaps remain explicit; no fault types, equipment identities, quality labels, or specifications are inferred.

Primary references: [Mendeley V2 release](https://data.mendeley.com/datasets/pdnjz7zz5x/2), [author notebook](https://github.com/StephenGoldie/indpensim-notebook), and [Goldrick et al. (2019)](https://doi.org/10.1016/j.compchemeng.2019.05.037), particularly Table 1. The exact headers in the contract were checked against the original archive; the original misspellings are preserved in `variables.source_header`.

## Selected numeric variables

All 33 selected values use Arrow `float64`. The first 30 are columns of `samples.parquet`; the last three are columns of `batches.parquet`. Raw positions are zero-based within the indicated CSV. The contract preserves each number without unit conversion, interpolation, smoothing, or imputation.

`unit_status=reported_only` means the source unit string was retained. `unresolved` marks a known scale or convention ambiguity; it does not supply a corrected unit. `offline_sparse` alone permits a literal source `NaN` to become Parquet null; other selected numeric columns are non-nullable.

| Output column | Raw position | Documented meaning | Reported unit | Unit status / kind | Boundary or observed fact |
| --- | ---: | --- | --- | --- | --- |
| `aeration_rate` | 1 | Aeration flow rate | `L/h` | `reported_only` / `process_value` | Published Fg channel; no gas-flow calibration or reference conditions supplied. |
| `agitator_rpm` | 2 | Agitator rotational speed | `RPM` | `reported_only` / `process_value` | Observed constant 100 throughout this release. |
| `sugar_feed_rate` | 3 | Sugar/substrate feed flow rate | `L/h` | `reported_only` / `process_value` | Fs channel. Do not conflate feed flow with substrate concentration. |
| `acid_flow_rate` | 4 | Acid addition flow rate | `L/h` | `reported_only` / `process_value` | Fa channel; no acid formulation or concentration metadata selected. |
| `base_flow_rate` | 5 | Base addition flow rate | `L/h` | `reported_only` / `process_value` | Fb channel; no base formulation or concentration metadata selected. |
| `heating_cooling_water_flow_rate` | 6 | Heating/cooling water flow rate | `L/h` | `reported_only` / `process_value` | Keep the combined Fc source meaning; no equipment circuit identifier. |
| `heating_water_flow_rate` | 7 | Heating water flow rate | `L/h` | `reported_only` / `process_value` | Fh channel; separate from Fc. |
| `water_injection_rate` | 8 | Water for injection/dilution flow rate | `L/h` | `reported_only` / `process_value` | Fw channel; source provides no water-lot record. |
| `air_head_pressure` | 9 | Air head pressure | `bar` | `reported_only` / `process_value` | Published pressure channel; absolute versus gauge convention is not verified. |
| `dumped_broth_flow` | 10 | Dumped broth flow | `L/h` | `reported_only` / `process_value` | Fremoved channel; observed values include negatives. Preserve their published sign. |
| `substrate_concentration` | 11 | Substrate concentration | `g/L` | `reported_only` / `process_value` | S channel; a simulator process value, not an available offline substrate assay. |
| `dissolved_oxygen` | 12 | Dissolved oxygen concentration | `mg/L` | `reported_only` / `process_value` | DO2 channel; do not treat mg/L as percent saturation. |
| `penicillin_concentration` | 13 | Penicillin concentration | `g/L` | `reported_only` / `process_value` | P process channel; distinct from the sparse offline penicillin channel and harvest summaries. |
| `vessel_volume` | 14 | Vessel liquid volume | `L` | `reported_only` / `process_value` | V channel; no vessel equipment identity or validated capacity specification. |
| `vessel_weight` | 15 | Vessel weight | `Kg` | `reported_only` / `process_value` | Wt channel; retain published numeric scale and label. |
| `ph` | 16 | pH | `pH` | `reported_only` / `process_value` | Dimensionless quantity. The source unit label is literally pH. |
| `temperature` | 17 | Temperature | `K` | `reported_only` / `process_value` | T channel; values remain Kelvin, with no Celsius conversion. |
| `generated_heat` | 18 | Generated heat | `kJ` | `reported_only` / `process_value` | Q channel; retain source label. No heat-meter or cumulative/incremental interpretation is added. |
| `co2_offgas` | 19 | Carbon dioxide in off-gas | `%` | `reported_only` / `process_value` | CO2outgas channel. Published as percent; physical calibration is unverified. |
| `paa_flow_rate` | 20 | Phenylacetic acid feed flow rate | `L/h` | `reported_only` / `process_value` | Fpaa channel; PAA expansion is documented in the paper. |
| `paa_offline` | 21 | Offline phenylacetic acid concentration | `g L^{-1}` | `unresolved` / `offline_sparse` | CSV label says g/L; paper Table 1 reports PAA in mg/L. Scale unresolved; no conversion. |
| `oil_flow_rate` | 22 | Oil feed flow rate | `L/hr` | `reported_only` / `process_value` | Foil channel; L/hr is retained as the source unit string. |
| `nh3_offline` | 23 | Offline ammonia concentration | `g L^{-1}` | `unresolved` / `offline_sparse` | CSV label says g/L; paper describes nitrogen in mg/L, without proving an NH3-to-N conversion. Preserve raw scale. |
| `oxygen_uptake_rate` | 24 | Oxygen uptake rate | `g min^{-1}` | `reported_only` / `process_value` | OUR channel; source reports g/min. Observed negative values are preserved, not clipped. |
| `o2_offgas` | 25 | Oxygen in off-gas | `%` | `unresolved` / `process_value` | Header says percent; observed 0.1295–0.22751 suggests a possible fraction convention. Convention unresolved. |
| `penicillin_offline` | 26 | Offline penicillin concentration | `g L^{-1}` | `reported_only` / `offline_sparse` | Sparse P_offline values; not released-product potency or acceptance results. |
| `biomass_offline` | 27 | Offline biomass concentration | `g L^{-1}` | `reported_only` / `offline_sparse` | Sparse X_offline values; no continuous biomass sensor is established. |
| `carbon_evolution_rate` | 28 | Carbon evolution rate | `g/h` | `reported_only` / `process_value` | CER channel; source reports g/h. Do not harmonize automatically with OUR units. |
| `ammonia_shots` | 29 | Ammonia shots | `kgs` | `reported_only` / `process_value` | NH3_shots channel; observed constant zero. A per-shot event table is not present. |
| `viscosity_offline` | 30 | Offline viscosity | `centPoise` | `reported_only` / `offline_sparse` | Sparse viscosity channel; source centPoise corresponds to the paper viscosity label cP. |
| `harvest_during_batch_raw` | 1 | Penicillin harvested during the batch | `kg` | `unresolved` / `raw_summary` | Raw summary from statistics, under a kg header. Scale and aggregation remain unresolved. |
| `harvest_end_of_batch_raw` | 2 | Penicillin harvested at batch end | `kg` | `unresolved` / `raw_summary` | Raw summary from statistics. Not established as equal to the final P times vessel volume. |
| `harvest_total_raw` | 3 | Total penicillin yield | `kg` | `unresolved` / `raw_summary` | Raw summary from statistics. Not a validated physical kg result, quality outcome, or pass/fail target. |

The three harvest variables use the statistics member; all others use the time-series member. Their source positions therefore overlap intentionally. Variable identity is `(dataset_id, output_table, output_column)`, represented by the stable `variable_id`; a raw position alone is not globally unique.

### Sparse values and time

**Observed:** `paa_offline`, `nh3_offline`, `penicillin_offline`, `biomass_offline`, and `viscosity_offline` each contain 2,062 finite values and 111,873 `NaN` entries in the source. Other selected process fields have no source nonfinite values. Null means no numeric value at that stored time; it must not become zero.

**Documented:** paper Table 1 describes 12-minute online values and 12-hour offline measurements with a four-hour analysis delay. **Observed:** stored offline values commonly appear at 1 h, multiples of 12 h, and the batch endpoint. There are no separate sample-collection and result-availability timestamps. The normalized `time_h` is the stored elapsed batch time and cannot establish when an offline result was available to an operator.

**Observed unit conflicts:** source PAA values span 393.1–11,524 and NH3 values span 1,391.6–5,170 under g/L labels. The paper uses mg/L for PAA and nitrogen; this does not prove the correction for these exact exports. The harvest totals span 890,830–4,447,700 under kg headers and fail a simple end-inventory reconciliation. All six `unresolved` fields remain unchanged.

## Time, raw metadata, and labels in samples

| Output field | Raw position | Type | Meaning and limits |
| --- | ---: | --- | --- |
| `time_h` | 0 | float64 | Stored elapsed batch hours; all batches begin at 0.2 h. No absolute date. |
| `time_tick` | Derived from 0 | int32 | Exact integer `Decimal(time_h) / 0.2`; one tick is 12 minutes. Integral positive ticks are required. |
| `batch_ref` | 35 | int16 | Publisher-documented batch key despite the misleading `2-PAT control(PAT_ref:PAT ref)` header. |
| `fault_reference_raw` | 31 | int8 | Literal source `Fault reference` binary value. Observed 1 on 1,256 samples in batches 91–100. Its behavior suggests an active-window flag, but physical fault onset/clearance semantics and named fault types are not documented for this release. |
| `control_reference_raw` | 32 | int8 | Header documents 0 recipe-driven / 1 operator-controlled. Observed 1 in batches 31–60, 0 otherwise. Zero does not distinguish APC from recipe-driven batches. |
| `metadata_33_raw` | 33 | int16 | Header is `1- No Raman spec`. Observed 2 for batches 61–90 and 1 otherwise. Full semantics unresolved; not a verified Raman-presence flag. |
| `metadata_34_raw` | 34 | int16 | Header is ` 1-Raman spec recorded`, but values equal the batch key 1–100. Preserve as raw metadata; do not use as a device flag. |
| `batch_fault_flag_raw` | 36 | int8 | Header is `Batch reference(Batch_ref:Batch ref)`, but observed values are 0 for batches 1–90 and 1 for 91–100, matching statistics. Corroboration only; authoritative `fault_present` is taken from statistics. |

The raw header has 2,239 fields while every data row has 2,237 values. Positions 37 onward are excluded from normalization. The labels `Batch ID` and `Fault flag` at 37–38 contain large continuous-looking values and are not accepted as identifiers or labels. A 2,200-value tail likely represents Raman spectra, but exact axis alignment is unresolved. No corrected wavelength/wavenumber dictionary is created.

## Batch fields

| Field | Type | Meaning / derivation |
| --- | --- | --- |
| `dataset_id`, `batch_id` | string | Stable logical identifiers, defined below. |
| `batch_ref` | int16 | Statistics `Batch ref`, joined to time-series raw position 35; unique 1–100. |
| `fault_present` | bool | Statistics `Fault ref(0-NoFault 1-Fault)`: 0 → false; 1 → true. Means the batch contains a simulated fault; does not mean failed quality or a named fault type. |
| `control_regime` | string | Publisher ranges: 1–30 `recipe_driven`, 31–60 `operator_controlled`, 61–90 `apc_raman`, 91–100 `not_documented`. Fault-containing is not a control regime. |
| `harvest_during_batch_raw`, `harvest_end_of_batch_raw`, `harvest_total_raw` | float64 | Source statistics values, described above, unchanged. |
| `sample_count` | int32 | Count of observed normalized samples in the batch. |
| `time_start_h`, `time_end_h` | float64 | First/last stored elapsed time for the batch; observed endpoints range 167–290 h. |
| `source_file_id`, `source_row_number` | string, int32 | Statistics member ID and one-based statistics data-record number. |
| `timeseries_first_source_row`, `timeseries_last_source_row` | int32 | First/last time-series data-record numbers contributing samples to this batch. |

## IDs, provenance, and variable metadata

| Field or identifier | Binding |
| --- | --- |
| `dataset_id` | `indpensim:pdnjz7zz5x:v2`; identifies Mendeley release `10.17632/pdnjz7zz5x.2`. |
| `batch_id` | `{dataset_id}:batch:{batch_ref:03d}`; e.g. `indpensim:pdnjz7zz5x:v2:batch:091`. |
| `sample_id` | `{batch_id}:tick:{time_tick:06d}`; batch 91 at 20 h is `indpensim:pdnjz7zz5x:v2:batch:091:tick:000100`. |
| `variable_id` | `{dataset_id}:variable:{output_column}`; stable across rebuilds with this contract. |
| `source_file_id` | `{dataset_id}:timeseries` or `{dataset_id}:statistics`; resolves through `manifest.source.members`. |
| `source_row_number` | One-based data-record number, excluding the header, globally within the member CSV. It is provenance, not a stable semantic identity. |
| `variables.output_table`, `variables.output_column` | Exact target table and column name, linking metadata to a wide numeric field. |
| `variables.source_column_index`, `variables.source_header` | Zero-based source position and exact original header, including spelling and misleading metadata. |
| `variables.unit_reported`, `unit_status`, `measurement_kind` | Published unit string and the explicit caution/kind categories defined above. |
| `manifest.source.sha256`, member `path`, `bytes`, `crc32` | Original archive integrity and member locations, including excluded data. |
| `manifest.cache_key`, `cache_inputs`, `outputs` | Build provenance and integrity checks, not dataset identity or observation time. |

The manifest retains the DOI, source URL, CC BY 4.0 attribution/license information, normalization warnings, contract/normalizer hashes, and writer environment. No run timestamp is inserted into deterministic artifacts. Source-file IDs join to the manifest, while row/column coordinates locate a source cell.

## Unsupported interpretations

No verified field identifies equipment, maintenance, calibration, material lots, individual operators, quality release decisions, sterility/potency/impurity results, or approved specifications. Do not derive these entities from a vessel process variable or binary fault label. Paper Campaign 4 fault examples are not a fault-type lookup for release batches 91–100. A zero sample-level flag does not establish that all downstream fault effects have disappeared.

Any future anomaly model must exclude stable IDs, source coordinates, binary labels and campaign metadata from its process-feature matrix unless their explicit modeling use is justified separately. The present milestone implements no anomaly model.
