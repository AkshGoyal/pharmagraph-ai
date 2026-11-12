# Retained evidence and portability

These are bounded validation examples and metadata, not the raw numerical dataset or a second application database. They carry the source dataset's attribution/terms where derived from it; see [dataset verification](../data_verification.md) and the [README attribution](../../README.md#dataset-attribution-and-terms).

| Directory | Retained purpose |
| --- | --- |
| `indpensim/` | Public source API metadata, recorded manifest, original inspection summary and ingestion/cache/rebuild acceptance |
| `graph/` | Exact node/edge counts, constraints, graph queries, source trace and standalone restart evidence |
| `investigation/` | Four original-data result examples, independent numerical comparison and detector test record |
| `demo/` | Real-data AppTest/HTTP acceptance, sanitized widget text and UI test record; no screenshots |
| `portfolio/` | Final documentation/hygiene checks and final full-suite output |

The four investigation JSON examples are retained because existing presentation tests use them. They include traceable observations and reference metadata, not full 113,935-row trajectories; the largest is approximately 1 MB. This is intentional reproducible evidence, rather than generated bulk data. Raw ZIPs/CSVs, Parquet caches, Neo4j stores/logs, runtime/JDK downloads, local investigation exports and credentials remain ignored. Ignored papers/images downloaded during source research remain local and are not a license grant or portfolio asset.

Historical commands mentioning `/private/tmp/` describe the original validation workspace; they are not prerequisites for a reviewer. Current setup uses repository-relative paths in the [README](../../README.md). The original user-specific repository prefix in `indpensim/ingestion_acceptance.json` has been normalized to `<repo>/`, with that change explicitly recorded in its `path_normalization` field. Source/output hashes, measurement values, counts and timings were not changed. Package build-source paths inside historical library warnings are diagnostic provenance, not application dependencies.

Do not treat a skipped test, framework AppTest result or standalone restart as proof of a browser interaction or Docker container persistence. Those verification boundaries are preserved in the reports.
