# Configuration benchmark plan

The executable workload is `benchmarks/configuration.py`; run it with `make bench` after `make install` has installed the repository's development requirements. It writes a raw JSON result under `benchmarks/results/` with Python/platform identity, dependency versions, input digests, and a source manifest fingerprint. Before timing, it compares the Pydantic Settings integration against the pinned 0.1.0 reference. Results below are historical exploratory artifacts; use a fresh run on the current commit before making a current performance claim.

## Questions the benchmark must answer

1. How expensive is a fresh settings or manager instance loading YAML with an interpolation variable set?
2. What is the cost of repeated top-level and nested lookups after loading?
3. What are the costs of schema validation, interpolation, and reload separately?
4. How does peak memory change as configuration size grows?
5. Do the measured operations preserve the expected resolved values and reference behavior?

## Workloads

The implementation generates 20, 500, and 3,000 nested sections. Each includes typed scalar values, booleans, lists, limits, and an environment-interpolated endpoint. It measures target and reference Pydantic Settings loads, direct configuration interpolation, Pydantic validation of an already-loaded mapping, 10,000 warm path lookups, directory merge, explicit reload, and peak allocation. Every workload checks the resolved input, reference parity, and validation result before timing. The measured loads create fresh settings or manager instances, but run in a process with imports already loaded and a warm OS file cache. The suite does not measure process startup, cold storage, TOML, environment-source precedence, or concurrent throughput; those results must come from separate workloads.

## Fair comparison rules

- Use the same machine, Python build, process conditions, and input files.
- Pin and report each competitor version.
- Match source inputs, precedence, validation, interpolation, and observable output.
- Report process startup or cold-storage behavior only when those boundaries are measured separately from these warm-cache loads.
- Run at least five paired samples in alternating target/reference order; report medians, median absolute deviations, and raw samples.
- Record the warm file-cache boundary, workload digest, source manifest fingerprint, Python and dependency versions, CPU model, architecture, and available memory.
- Publish raw output and the exact command.
- Report latency together with memory and correctness results. This single-process suite does not establish concurrent throughput.
- Do not omit a competitor feature that adds required work simply to improve its score.

## Results

Exploratory paired run on CPython 3.12.11, Linux x86_64, AMD Ryzen 5 2600X, dated 2026-10-11. The checkout was dirty and had no Git revision available. The five samples alternate target/reference order after a correctness preflight, so file data and imports are warm; process startup is not measured. The follow-up run uses the same workload and machine after reducing interpolation and traversal overhead. These numbers are directional, not a release performance claim.

| Workload | Standard settings load | Reference settings load | Descriptive ratio | Warm lookup | Peak memory |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20 sections / 3.7 KB | 3.07 ms | 17.58 ms | 5.72× | 5.51 µs | 0.16 MiB |
| 500 sections / 93.0 KB | 67.39 ms | 439.92 ms | 6.53× | 5.53 µs | 3.91 MiB |
| 3,000 sections / 567.3 KB | 522.90 ms | 2,709.93 ms | 5.18× | 5.52 µs | 25.17 MiB |

The settings workload includes typed Pydantic models and 20, 500, or 3,000 nested interpolated endpoints. The separate Standard interpolation loads were 2.88 ms, 68.54 ms, and 430.94 ms; Pydantic-only validation was 43.20 µs, 1.09 ms, and 7.54 ms; directory merge was 3.98 ms, 68.75 ms, and 433.87 ms. All three workloads matched the live reference and resolved input before timing. Each input has a recorded SHA-256 digest and every measurement retains its five raw samples and median absolute deviation.

The follow-up raw samples and environment details are in [configuration-20261011T174138Z.json](../../benchmarks/results/configuration-20261011T174138Z.json); the initial measurements are retained in [configuration-20261011T172326Z.json](../../benchmarks/results/configuration-20261011T172326Z.json). Compared with the initial target medians, the follow-up is 14%–20% faster while the reference medians changed by less than 3%; peak allocation is unchanged. The descriptive settings-load ratio is 5.18×–6.53×, still well below the original 100× aspiration. No 100× claim is made. Power mode is unknown, and neither run has an immutable Git revision.

A corrected fresh-install benchmark with current compatible dependencies is recorded in [configuration-20261011T180833Z.json](../../benchmarks/results/configuration-20261011T180833Z.json). It ran on CPython 3.12.11 with Pydantic 2.14.0, pydantic-settings 2.15.0, PyYAML 6.0.3, and the same pinned 0.1.0 reference:

| Workload | Standard settings load | Reference settings load | Descriptive ratio | ConfigManager load | Pydantic-only validation |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20 sections | 2.99 ms | 17.53 ms | 5.86× | 2.88 ms | 0.04 ms |
| 500 sections | 73.06 ms | 432.51 ms | 5.92× | 70.06 ms | 1.02 ms |
| 3,000 sections | 533.81 ms | 2,723.75 ms | 5.10× | 433.76 ms | 6.50 ms |

This is a compatibility check against newer dependency versions, not a direct optimization comparison with the earlier run because Pydantic and pydantic-settings versions differ. An earlier current-dependency artifact, [configuration-20261011T175938Z.json](../../benchmarks/results/configuration-20261011T175938Z.json), is retained, but its `pydantic_validation_only` measurement is superseded: it called `YamlSettings.model_validate`, which also ran settings sources in that Pydantic Settings version. The corrected workload validates the same mapping with a plain Pydantic model. The 100× aspiration remains unmet.

An additional paired run with `pydantic-settings` 2.6.0, Pydantic 2.12.5, and PyYAML 6.0.3 is recorded in [configuration-20261011T182048Z.json](../../benchmarks/results/configuration-20261011T182048Z.json). It measured 3.14 ms vs 17.59 ms for 20 sections (5.60×), 68.03 ms vs 443.89 ms for 500 sections (6.53×), and 534.60 ms vs 2,743.81 ms for 3,000 sections (5.13×); the large `ConfigManager` load was 438.02 ms. This is a separate dependency-version result, not a direct comparison with the 2.15.0 run.

A cProfile diagnostic on that 3,000-section workload attributed 0.762 s of a 1.074 s `ConfigManager` profile to YAML reading and construction, 0.197 s to recursive interpolation, and about 0.110 s to snapshot freezing. These profiled timings include instrumentation overhead and are diagnostic only. A five-sample parse-only experiment measured the current custom `CSafeLoader` path at 0.343 s median; plain `CSafeLoader` followed by equivalent recursive key validation measured 0.349 s, so that alternative was rejected. YAML construction remains the dominant measured path, and no 100× result has been demonstrated.

A loader-owned in-place snapshot-freeze prototype was also measured and reverted. The pre-change baseline is [configuration-20261011T182048Z.json](../../benchmarks/results/configuration-20261011T182048Z.json), and the candidate run is [configuration-20261011T182943Z.json](../../benchmarks/results/configuration-20261011T182943Z.json); they use the same runtime, dependency versions, and input digests. For 3,000 sections, the `ConfigManager` median moved from 438.02 ms to 436.42 ms (0.37%), while the candidate median absolute deviation rose from 2.89 ms to 6.68 ms and peak memory remained 25.17 MiB. This does not establish a repeatable whole-call gain or a memory reduction, so the final implementation retains defensive snapshot copying. Do not attribute the candidate result to the current implementation.

A fresh run against the current implementation is recorded in [configuration-20261011T190732Z.json](../../benchmarks/results/configuration-20261011T190732Z.json). It used CPython 3.12.11, Pydantic 2.12.5, pydantic-settings 2.6.0, and PyYAML 6.0.3 on the same Ryzen 5 2600X. Each case passed the reference, resolved-input, interpolation, validation, and directory-merge preflights before timing.

| Workload | Standard settings load | Reference settings load | Ratio | ConfigManager load | Warm lookup | Peak memory |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 sections / 3.7 KB | 3.19 ms | 17.54 ms | 5.49× | 2.88 ms | 5.38 µs | 0.16 MiB |
| 500 sections / 93.0 KB | 68.42 ms | 440.46 ms | 6.44× | 69.46 ms | 5.38 µs | 3.91 MiB |
| 3,000 sections / 567.3 KB | 535.22 ms | 2,760.83 ms | 5.16× | 443.70 ms | 5.38 µs | 25.17 MiB |

The ratios compare the full Pydantic Settings boundary with the 0.1.0 reference; they are descriptive results, not a claim that this project is 100× faster. The run used five samples and warm OS file cache, and the checkout had no immutable Git revision. Its measurements include medians, median absolute deviations, raw samples, and input digests.

The latest five-sample run, produced with `make bench` on 2026-10-12, is [configuration-20261012T004412Z.json](../../benchmarks/results/configuration-20261012T004412Z.json). It used CPython 3.12.11, Pydantic 2.12.5, pydantic-settings 2.6.0, PyYAML 6.0.3, and the pinned 0.1.0 reference on the same Ryzen 5 2600X. All preflight checks passed. The checkout still has no Git revision, so this artifact records a source manifest SHA-256 (`7e7c6f3561c48e4bb7e89276ad20fa858df38e09d75eb868b1e00d4f254c8785`) over the benchmark, configuration implementation, and dependency declarations.

| Workload | Standard settings load | Reference settings load | Descriptive ratio | ConfigManager load | Warm lookup | Peak memory |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 sections / 3.7 KB | 3.49 ms | 17.69 ms | 5.07× | 2.86 ms | 5.34 µs | 0.16 MiB |
| 500 sections / 93.0 KB | 67.26 ms | 434.94 ms | 6.47× | 68.40 ms | 5.44 µs | 3.91 MiB |
| 3,000 sections / 567.3 KB | 532.74 ms | 2,743.82 ms | 5.15× | 432.27 ms | 5.31 µs | 25.17 MiB |

These are warm-cache, single-process measurements; process startup, cold storage, TOML, environment-source precedence, and concurrent throughput are outside this suite. The descriptive ratio is still far below the original 100× aspiration, which remains unmet.

A scalar-resolution fast path was considered and rejected. The seven-sample baseline and candidate artifacts are [configuration-20261011T191020Z.json](../../benchmarks/results/configuration-20261011T191020Z.json) and [configuration-20261011T191136Z.json](../../benchmarks/results/configuration-20261011T191136Z.json). On the large workload, their `ConfigManager` medians were 440.32 ms and 431.84 ms, but the target and reference measurements both moved between runs. A dedicated nine-pair comparison then used the same 567,310-byte input and checked resolved values after every load: the candidate won only three pairs, and the paired median was 10.43 ms slower. The raw paired measurements and decision are in [configuration-resolver-ab-20261012.json](../../benchmarks/results/configuration-resolver-ab-20261012.json). The experiment is reverted; the current resolver retains location tracking and cycle detection on every nested value.

A fresh cProfile diagnostic of the 3,000-section `ConfigManager.from_file` path took 1.043 s under instrumentation: YAML reading and construction accounted for 0.763 s, recursive interpolation for 0.166 s, and snapshot freezing for 0.110 s. These are profiled diagnostic timings, not production latency measurements. They indicate that resolver-only changes have limited room to improve end-to-end load time; they do not establish a forecast for replacing the YAML parser.

### Parser candidates screened, not adopted

The [`pyfastyaml` 0.2.0 package description](https://pypi.org/project/pyfastyaml/0.2.0/) advertises 12–18× parsing speed over PyYAML's C loader on its own fixtures. Its PyPI metadata marks it beta and lists Python classifiers through 3.13; its package description requires a C++17 compiler and limits compatibility to typical configuration YAML, with custom tags and complex flow keys unsupported. The current loader subclasses PyYAML's C safe loader to reject non-string mapping keys at their source location. `pyfastyaml` does not document that loader subclass hook, so its headline parser result does not establish equivalent behavior or an end-to-end gain for this project. Treat it as an unvalidated research candidate until support is declared for the full Python matrix and it passes the configuration behavior contract and paired whole-call benchmark.

The [`rapidyaml-python` README](https://github.com/biojppm/rapidyaml-python) reports much higher parse speed, but its Python wrapper returns a low-level tree with untyped scalar string views rather than materialized Python dictionaries, lists, and typed scalar values. Its own benchmark note says the comparison is biased because that Python conversion work is omitted. Materialization and typing would need to be included before those results could be compared with `ConfigManager`. [`msgspec` installation docs](https://msgspec.dev/install) also show that its YAML optional dependency is PyYAML, so it is not a parser replacement.

These projects' published numbers are research leads, not measurements of Standard. Keep PyYAML as the production loader until a candidate passes semantic parity and demonstrates a repeatable gain at the complete configuration-load boundary.

## Implementation order

Use the [configuration behavior contract](index.md) as the parity bar and build compatibility cases before optimizing. Measure a clear, correct baseline first. Keep each optimization only when the benchmark shows a repeatable gain without changing behavior or weakening validation.
