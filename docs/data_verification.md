# IndPenSim dataset verification

Verified on **30 October 2026 (Asia/Kolkata)**. Scope: source research, access checks, download, and inspection only. No application, model, synthetic replacement data, or product acceptance rules were built.

## Result and evidence conventions

**The author-published dataset is publicly downloadable, and the original archive was downloaded successfully.** Its size and SHA-256 match the official Mendeley file manifest. All 113,935 time-series records and all 100 statistics records were inspected.

There are material limitations: malformed time-series headers, misleading metadata names, unresolved unit/harvest inconsistencies, and no verified mapping from the release's binary fault indicators to named fault types. The dataset supports investigation of simulated batch trajectories, with these limitations retained explicitly.

- **Documented:** explicitly stated by the publisher, author notebook, paper, license, or source header. A source header establishes a published label, not necessarily a correct physical unit.
- **Observed:** measured from the downloaded original bytes.
- **Inference:** a possible interpretation supported by observations but not established by the available documentation.
- **Unknown:** not verified. No values or meanings have been supplied to fill these gaps.

Machine-readable observations are saved in [inspection.json](evidence/indpensim/inspection.json). The read-only [inspection script](../scripts/verify_indpensim.py) preserves raw positions and does not repair or overwrite the source data.

## 1. Authoritative source and documentation

| Resource | URL | Verification |
| --- | --- | --- |
| Selected author-published release | https://data.mendeley.com/datasets/pdnjz7zz5x/2 | Stephen Goldrick; version 2; published 8 October 2019; DOI `10.17632/pdnjz7zz5x.2`; CC BY 4.0 |
| DOI | https://doi.org/10.17632/pdnjz7zz5x.2 | Persistent identifier for the selected release |
| University provenance | https://research.manchester.ac.uk/en/datasets/data-for-modern-day-monitoring-and-control-challenges-outlined-on/ | University record corroborates the author, release DOI, and license |
| Author's notebook | https://github.com/StephenGoldie/indpensim-notebook | Explicitly linked by Mendeley; inspected `IndPenSim_Summary_data_notebook_V3.ipynb` |
| Notebook raw download | https://raw.githubusercontent.com/StephenGoldie/indpensim-notebook/master/IndPenSim_Summary_data_notebook_V3.ipynb | Downloaded: 391,224 bytes; inspected as JSON without executing its code |
| 2019 benchmark paper | https://doi.org/10.1016/j.compchemeng.2019.05.037 | Goldrick et al., *Modern day monitoring and control challenges outlined on an industrial-scale benchmark fermentation process* |
| Open paper PDF | https://discovery.ucl.ac.uk/id/eprint/10082538/7/Goldrick_Modern%20day%20monitoring%20and%20control%20challenges%20outlined%20on%20an%20industrial-scale%20benchmark%20fermentation%20process_VoR.pdf | Downloaded: 4,810,481 bytes; extracted 14 pages; visually checked Table 1 (page 3) and Figure 7 (page 10) |
| Original simulator paper | https://doi.org/10.1016/j.jbiotec.2014.10.029 and https://pubmed.ncbi.nlm.nih.gov/25449107/ | Referenced by the dataset; not used to assign additional labels or specifications |
| Simulator/documentation site | http://www.industrialpenicillinsimulation.com/ and https://www.industrialpenicillinsimulation.com/ | Access failed; details below |
| Separate author publication | https://data.mendeley.com/datasets/npt257bjxn/1 | A distinct record, DOI `10.17632/npt257bjxn.1`, published 4 September 2019; not downloaded or assumed byte-identical |

**Documented:** this is simulated data for a 100,000-litre penicillin fermentation system, not actual GMP manufacturing records. Mendeley describes batches 1–30 as recipe-driven, 31–60 as operator-controlled, 61–90 as APC using Raman, and 91–100 as containing faults. The author specifically identifies `2-PAT control(PAT_ref:PAT ref)` as the batch reference. [Source: selected Mendeley release](https://data.mendeley.com/datasets/pdnjz7zz5x/2).

## 2. Download availability, sizes, integrity, and usage terms

### Successful access method

No login, access token, or payment was required. The current public API provided the archive's download location:

1. [Versioned metadata](https://data.mendeley.com/public-api/datasets/pdnjz7zz5x/snapshot/2), saved as [snapshot_v2.json](evidence/indpensim/snapshot_v2.json).
2. [Version-2 file manifest](https://data.mendeley.com/public-api/datasets/pdnjz7zz5x/files?folder_id=root&version=2&%24start=0&%24limit=1000), saved as [files_v2.json](evidence/indpensim/files_v2.json). Request header: `Accept: application/vnd.mendeley-public-dataset.1+json`.
3. [Download API](https://data.mendeley.com/public-api/datasets/pdnjz7zz5x/files/e7007dff-4061-494f-a9f5-16c20f457d1d/file_downloaded), saved as [download_api_response.json](evidence/indpensim/download_api_response.json).
4. The API returned [this official S3 object](https://prod-dcd-datasets-public-files-eu-west-1.s3.eu-west-1.amazonaws.com/e349116a-7ee5-4daf-ba5e-162ceeebff6b); downloading it succeeded. Storage URLs may change, so resolve them through the API when repeating the download.

The original ZIP is retained locally at `data/raw/indpensim/100_Batches_IndPenSim.zip`, excluded from Git to avoid committing a 504 MB archive. CSVs were streamed from the archive without altering or expanding the original files on disk.

| Item | Exact size | Status |
| --- | ---: | --- |
| `100_Batches_IndPenSim.zip` | 503,792,426 bytes | Downloaded; equals manifest size, approximately 503.79 MB / 480.45 MiB |
| Combined uncompressed CSV contents | 2,566,831,530 bytes | Observed ZIP member sizes; explains the publisher's approximate 2.5 GB description |
| Mendeley generated Download All archive | 494,905,983 bytes | API reports `FINISH`; not downloaded or verified; distinct packaging, not interchangeable checksums |

Published and locally computed SHA-256 of the original archive:

```text
bc434c6cf96444fee3c915d434ac84e2a9c6492be4daebcfa4aed9cdff181f00
```

Both CSV members were read to EOF, including ZIP CRC verification by Python's `zipfile` reader. Reproduce the inspection after obtaining the original ZIP:

```sh
shasum -a 256 data/raw/indpensim/100_Batches_IndPenSim.zip
python3 scripts/verify_indpensim.py
```

### Usage terms

**Documented:** Mendeley licenses the dataset under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with [legal code here](https://creativecommons.org/licenses/by/4.0/legalcode.en). The license permits sharing and adaptation, including commercial use, subject to attribution, a license link, and indicating changes. Do not imply endorsement or impose additional restrictions on the licensed material. Preserve supplied notices. The repository metadata additionally notes that separately identified third-party content may need further permission.

The publisher requests citation of the 2015 simulator paper and 2019 benchmark paper. Suggested dataset attribution:

> Goldrick, Stephen (2019), “Data for: Modern day monitoring and control challenges outlined on an industrial-scale benchmark fermentation process”, Mendeley Data, V2, doi:10.17632/pdnjz7zz5x.2. CC BY 4.0. State any subsequent transformations separately.

The paper PDF itself states **CC BY-NC-ND 4.0**, a different license from the data. Do not apply the dataset license to the paper or assume it licenses the notebook/simulator code. No independent notebook or simulator-code reuse license was verified.

### Access failures and alternatives

| Attempt | Exact result | Alternative and disposition |
| --- | --- | --- |
| Initial sandboxed notebook download | `curl: (6) Could not resolve host: raw.githubusercontent.com` | Retried with approved network access; notebook downloaded successfully. Environment restriction, not evidence of a missing dataset. |
| Simulator HTTPS website | Web tool: `(502) Bad Gateway`. Direct curl: exit 35, `LibreSSL/3.3.6: error:1404B438:SSL routines:ST_CONNECT:tlsv1 alert internal error` | Used author-published Mendeley metadata, author notebook, and institutional paper copy. HTTP through the web tool also resolved to HTTPS and failed. Website-only documentation remains unavailable. |
| Notebook's literal historical URL: `https://data.mendeley.com//datasets/pdnjz7zz5x//1//files//ec0dfb55-7e3c-4124-8b0c-ca8ae7c50fe7//100_Batches_IndPenSim.zip` | HTTP 404, curl exit 56 | Resolved the current public file manifest. The obsolete URL uses a content ID; current download routing uses a different file ID. |
| Normalized version-2 `/datasets/.../files/ec0dfb55-.../100_Batches_IndPenSim.zip` route | HTTP 301 to `/v1/datasets/...`, then HTTP 404 | Same official API route used instead. |
| Initial API guesses `/public-api/datasets/pdnjz7zz5x/versions/2` and `/versions/2/files` | HTTP 404 | Read the public page's download-client routes; `/snapshot/2` and `/files?version=2...` succeeded. |
| Manifest's `/public-files/.../file_downloaded` handler | HTTP 200 but **404-byte JSON error body**, not a ZIP: `invalid json response body ... reason: Unexpected token 'S', ... Service Unavailable ... is not valid JSON` | Rejected the response as data; saved [download_error.json](evidence/indpensim/download_error.json). Calling `/public-api/.../file_downloaded` directly returned `status: OK` and the successful storage URL. |
| PDF screenshot via web tool | `Timeout fetching`, then `Cache miss` | Direct PDF download succeeded; rendered and inspected locally with macOS PDFKit. |

The official [Download All API](https://data.mendeley.com/api/datasets-v2/datasets/pdnjz7zz5x/zip?version=2) is another access route; its response is preserved in [archive_api_response.json](evidence/indpensim/archive_api_response.json). No replacement dataset or third-party repackaging was selected.

## 3. Actual files, schema, units, identifiers, and time resolution

### Archive inventory

| Actual ZIP member | Uncompressed bytes | Contents |
| --- | ---: | --- |
| `Mendeley_data/` | 0 | Directory |
| `Mendeley_data/100_Batches_IndPenSim_Statistics.csv` | 3,904 | 100 data rows, 5 columns, one row per batch |
| `Mendeley_data/100_Batches_IndPenSim_V3.csv` | 2,566,827,626 | 113,935 data rows; 2,239 header fields but **2,237 values in every data row** |

No README, fault-type dictionary, equipment table, batch release records, or specification file is included in this ZIP.

### Time-series process fields

The following are **raw zero-based column positions**, before any rename. Positions 0–30 can be inspected independently of the later header discrepancy. Units below reproduce source labels; they are not independently calibrated units. Exact original headers, ranges, missingness, and sample values are retained in `inspection.json`.

| Position | Variable / source symbol | Header unit |
| ---: | --- | --- |
| 0 | Time | h |
| 1 | Aeration rate, Fg | L/h |
| 2 | Agitator speed, RPM | RPM |
| 3 | Sugar feed rate, Fs | L/h |
| 4 | Acid flow rate, Fa | L/h |
| 5 | Base flow rate, Fb | L/h |
| 6 | Heating/cooling water flow rate, Fc | L/h |
| 7 | Heating water flow rate, Fh | L/h |
| 8 | Water for injection/dilution, Fw | L/h |
| 9 | Air head pressure | bar |
| 10 | Dumped broth flow, Fremoved | L/h |
| 11 | Substrate concentration, S | g/L |
| 12 | Dissolved oxygen concentration, DO2 | mg/L |
| 13 | Penicillin concentration, P | g/L |
| 14 | Vessel volume, V | L |
| 15 | Vessel weight, Wt | `Kg` |
| 16 | pH | `pH` (dimensionless quantity) |
| 17 | Temperature, T | K |
| 18 | Generated heat, Q | kJ |
| 19 | Carbon dioxide in off-gas, CO2outgas | % |
| 20 | PAA flow, Fpaa | L/h |
| 21 | Offline PAA concentration, PAA_offline | `g L^{-1}`; unresolved scale, see below |
| 22 | Oil flow, Foil | L/hr |
| 23 | Offline NH3 concentration, NH3_offline | `g L^{-1}`; unresolved scale, see below |
| 24 | Oxygen uptake rate, OUR | `g min^{-1}` |
| 25 | Oxygen in off-gas, O2 | %; unresolved numerical convention |
| 26 | Offline penicillin concentration, P_offline | `g L^{-1}` |
| 27 | Offline biomass concentration, X_offline | `g L^{-1}` |
| 28 | Carbon evolution rate, CER | g/h |
| 29 | Ammonia shots, NH3_shots | `kgs` |
| 30 | Offline viscosity, Viscosity_offline | `centPoise` |

**Observed:** RPM is 100 throughout, and NH3_shots is 0 throughout. These fields provide context but no variation for this release. Only positions 21, 23, 26, 27, and 30 contain nonfinite values among positions 0–36: each has 111,873 `NaN` entries and 2,062 finite entries. No nonnumeric values were found in positions 0–36.

### Metadata and header defects

| Position | Literal raw header | Observed values / interpretation |
| ---: | --- | --- |
| 31 | `Fault reference(Fault_ref:Fault ref)` | 0/1, varying within fault-containing batches; see fault section |
| 32 | `0 - Recipe driven 1 - Operator controlled(Control_ref:Control ref)` | 1 for batches 31–60; 0 for all others. Zero alone cannot distinguish recipe-driven from APC. |
| 33 | `1- No Raman spec` | 2 for batches 61–90; 1 otherwise. **Unknown full semantics:** do not interpret the literal header as proving spectra are absent. |
| 34 | ` 1-Raman spec recorded` | Equals the documented batch key at position 35 throughout; values 1–100. Header is misleading; not a verified Raman-presence flag. |
| 35 | `2-PAT control(PAT_ref:PAT ref)` | **Documented batch identifier**, values 1–100. Join to statistics `Batch ref` here. |
| 36 | `Batch reference(Batch_ref:Batch ref)` | 0 for batches 1–90; 1 for 91–100. Matches the statistics fault indicator, despite the header. |
| 37 | `Batch ID` | Sample values are large, continuous-looking numbers after the initial zeros. Not a valid batch key. |
| 38 | `Fault flag` | Sample values are large, continuous-looking numbers after the initial zeros. Not a verified fault label. |
| 39–2238 in header | Numeric labels `2400`, `2399`, …, `201` | 2,200 putative spectral labels; row data end at position 2236. |

**Documented:** the author notebook swaps the names at positions 35 and 36. **Observed:** the second column after that rename has a batch-wide binary fault indicator; it does not behave like a PAT-control setting. The notebook's rename is useful for the batch key but does not resolve all misleading metadata headers.

**Observed structural mismatch:** after the first 37 values, each row has exactly 2,200 remaining values. The header instead inserts `Batch ID` and `Fault flag` before its 2,200 numeric spectral labels. A naive header-based loader can therefore misname spectral values and pad the final two columns as missing.

**Inference, not an applied repair:** the 2,200-value tail likely represents spectra and `Batch ID` / `Fault flag` are extraneous header entries. This would align a candidate axis of 2400 down to 201, but the exact axis alignment has not been verified against the original export code. No repaired Raman schema was selected. Raman intensity calibration units are not established by the CSV; the author notebook uses a generic intensity label and an axis in cm^-1. Treat these as spectral coordinates, not calendar time or equipment identifiers.

**Observed:** the tail is entirely zero for ten rows in every batch and has at least one nonzero entry in the other rows. This was checked as raw strings; a full numeric validity/physics audit of all tail values was not performed. The zeros are not evidence of an absent device or a fault label.

### Statistics schema

Exact published headers, including spelling:

| Header | Observed contents |
| --- | --- |
| `Batch ref` | Unique integer identifiers 1–100 |
| `Penicllin_harvested_during_batch(kg)` | Numeric harvest summary, published as kg; scale/reconciliation unresolved |
| `Penicllin_harvested_end_of_batch (kg)` | Numeric end harvest summary, published as kg; scale/reconciliation unresolved |
| `Penicllin_yield_total (kg)` | Numeric total harvest summary, published as kg; scale/reconciliation unresolved |
| `Fault ref(0-NoFault 1-Fault)` | Explicit binary meaning in header: 0 = no fault, 1 = fault |

These are harvest quantities, **not** released-product quality results or pass/fail decisions.

### Time resolution and batch duration

**Observed:** all batches start at elapsed time 0.2 h. Every one of the 113,835 within-batch time differences is 0.2 h (12 minutes, to eight decimal places). Batch end times range from 167.0 to 290.0 h; row counts range from 835 to 1,450. Time resets between batches. No absolute manufacturing dates or timestamps are present.

**Documented:** Table 1 of the [2019 paper](https://doi.org/10.1016/j.compchemeng.2019.05.037) describes 12-minute online measurements and 12-hour offline assays with a four-hour analysis delay. **Observed:** this CSV's five offline fields are sparse on the 12-minute grid, typically populated at 1 h, multiples of 12 h, and the batch endpoint. For batch 1, the final offline sample is at 226 h; for batch 2, at 230 h. Counts range from 15 to 26 per batch. Separate sample-collection and result-availability timestamps are absent; the paper's delay cannot be reconstructed reliably from these columns alone.

### Unit and harvest inconsistencies

- **PAA/NH3:** the CSV headers say g/L, but observed PAA is 393.1–11,524 and NH3 is 1,391.6–5,170. Table 1 documents PAA and nitrogen in mg/L. This is an unresolved unit/scale conflict; no conversion was applied.
- **Off-gas O2:** header says percent, but values range from 0.1295 to 0.22751. A fraction convention is plausible, but unverified. No multiplication by 100 was applied.
- **Harvest summaries:** total values range from 890,830 to 4,447,700 under headers marked kg. Do not use those numbers as validated kg or silently divide them by 1,000. A simple reconciliation also fails: batch 1's last stored P is 29.373 g/L and V is 78,799 L, giving `P × V / 1000 = 2,314.563027 kg`, whereas the statistics end-harvest entry is `1,720,000`. This does not establish a correction factor or prove that final vessel inventory should equal harvested mass. The aggregation basis and alignment need clarification.

No production specifications, accepted operating limits, or quality acceptance cutoffs are inferred from these ranges.

## 4. Fault labels: existence, storage, and documented meanings

**Verified batch labels exist.** Use statistics `Fault ref(0-NoFault 1-Fault)`: 90 batches are 0 (1–90), and 10 are 1 (91–100). This agrees with the author's release description. Raw time-series position 36 is the same binary value for every row in the respective batch, but its header is misleading.

**Observed time-varying indicator:** raw position 31, `Fault reference(Fault_ref:Fault ref)`, is 1 on 1,256 rows and 0 elsewhere. It is always 0 in batches 1–90. In batches 91–100 it changes as follows; endpoints below are **inclusive observed sample times**, not asserted physical onset/clearance times:

| Batch | Time windows where raw `Fault_ref = 1` (h) |
| ---: | --- |
| 91 | 20.0–30.0; 76.0–92.0; 200.0–214.0 |
| 92 | 80.0–84.0; 140.0–160.0 |
| 93 | 70.0–90.0 |
| 94 | 20.0–24.0; 100.0–110.0 |
| 95 | 20.0–30.0; 76.0–92.0; 200.0–211.0 (batch ends at 211.0) |
| 96 | 70.0–90.0 |
| 97 | 20.0–30.0; 76.0–92.0; 200.0–214.0 |
| 98 | 80.0–84.0; 140.0–160.0 |
| 99 | 20.0–24.0; 100.0–110.0 |
| 100 | 20.0–24.0; 100.0–110.0 |

**Limit of documentation:** the source header identifies a fault reference but does not supply a fault-type codebook or formal semantics for these sample-level 0/1 values. Their behavior is consistent with a fault-active flag; that interpretation is an inference. A zero inside a fault-containing batch must not be treated as proof that all process effects have ended.

**Documented paper examples are separate:** section 5.2 / Figure 7 of the [2019 paper](https://doi.org/10.1016/j.compchemeng.2019.05.037) associates Campaign 4 batches 18, 19, 20, and 21 with aeration, pH-sensor drift, substrate, and coolant faults, respectively. These are not documented mappings for release batches 91–100. In this downloaded release, batches 18–21 have batch fault label 0. No fault type, root cause, severity, injected magnitude, or equipment failure label has been assigned to batches 91–100. `Fault flag` at raw position 38 is not accepted as ground truth.

## 5. Verified fields supporting batch-level anomaly investigation

The following are potential uses of verified observations, not an implemented anomaly model:

| Investigation | Verified fields | Practical boundary |
| --- | --- | --- |
| Retrieve one batch and compare trajectories | Documented batch key at raw position 35; statistics `Batch ref`; elapsed `Time (h)` | IDs join across both files; variable lengths require an explicit comparison method |
| Compare control regimes | Author's batch ranges; raw Control_ref at 32; observed code at 33 | Compare within appropriate regimes; do not call normal APC differences faults |
| Investigate oxygen/gas changes | Aeration, DO2, O2 off-gas, CO2 off-gas, pressure, OUR, CER | Preserve original unit labels and unresolved conventions; association does not prove cause |
| Investigate feed/thermal/pH deviations | Fs, Fa, Fb, Fc, Fh, Fw, Foil, Fpaa, temperature, pH, heat, dumped broth, volume, weight | These are simulated trajectories; no equipment maintenance or controller set-point history was verified |
| Review product/growth trajectories | P, S, sparse P_offline, X_offline, PAA_offline, NH3_offline, viscosity | Distinguish simulator states from assay availability; preserve NaNs and unit uncertainty |
| Compare fault-containing batches and indicator windows | Explicit statistics fault label; raw position 31 transitions; raw 36 as corroboration | Binary labels only; exclude labels and identifiers from future anomaly-model inputs to avoid leakage |
| Review harvest summaries | Three published penicillin summary fields | Only as source-reported quantities until units and aggregation are reconciled; no product-release judgment |
| Investigate Raman patterns | Observed 2,200-value row tail | Block semantic spectral analysis until axis/header mapping is verified |

RPM and ammonia-shot fields are constant in this release. They cannot explain differences between these batches through variation in their recorded values.

## 6. Missing information and blockers

1. **Fault-type ground truth:** no verified per-batch type dictionary, severity, root-cause mapping, or injection configuration for this 100-batch release. The binary batch truth is usable; named diagnosis is not established.
2. **Raman/header mapping:** all rows are two values shorter than the header. The proposed 37-plus-2,200 layout is structurally plausible but requires exporter/source-code or author confirmation before assigning a corrected spectral axis. Metadata positions 33–34 also need explanation.
3. **Units and harvest provenance:** PAA/NH3 header units, O2 percent convention, and harvest summary scale/aggregation remain unresolved. Do not apply physical thresholds or quality outcomes using guessed corrections.
4. **Offline timing:** the documented four-hour delay has no separate collection/result timestamps in the CSV. Exact information availability for prospective monitoring is unknown.
5. **Unavailable simulator website:** recorded TLS/502 failures prevent verification of website-only manuals or original generation settings. Downloading third-party simulator forks or regenerating batches would not verify the published original release.
6. **Absent operational records:** no verified equipment identifiers, maintenance/work orders, calibration records, raw-material lots, operator identities, interventions log, deviation investigations, absolute production calendar, or validated specification table. A simulated vessel variable is not an equipment record.
7. **Absent product acceptance ground truth:** no release/reject labels, potency/impurity assays, sterility outcomes, or approved product specifications were found. Fault label 1 does not establish a failed product, and label 0 does not establish a conforming product.
8. **Coverage limit:** the inspection checked full row structure, process-field parsing/missingness, batch keys, time spacing, binary indicators, and archive integrity. It did not validate the simulator's physical accuracy, every numeric Raman value, or the unselected separate Mendeley publication.

The original dataset remains selected for verification. No replacement, additional fault taxonomy, quality outcome, equipment record, or specification has been invented.
