# PhantomOS Benchmark Methodology

Performance claims should be reproducible from this directory and should describe the current runtime rather than obsolete abstractions.

## Run

Install development dependencies:

```bash
pip install -e '.[dev]'
```

Smoke the benchmark code without timing:

```bash
pytest -q benchmarks --benchmark-disable --no-cov
```

Run timed benchmarks:

```bash
pytest benchmarks -q --benchmark-only --no-cov
```

For machine-readable comparison data:

```bash
pytest benchmarks -q --benchmark-only --no-cov --benchmark-json=benchmark.json
```

## Current microbenchmarks

`bench_tasks.py` measures:

- benign safety-policy authorization overhead;
- trigger matching across 1,001 recipes;
- rule-based intent recognition for a representative coding frame;
- recursive safety inspection of a 100-step sequence.

These are microbenchmarks, not claims about end-to-end desktop latency.

## Reporting requirements

When publishing performance numbers, record:

- PhantomOS commit SHA;
- operating system and version;
- CPU model;
- RAM;
- Python version;
- whether the machine was on battery or power;
- benchmark command;
- number of rounds/iterations;
- median and tail statistics reported by pytest-benchmark.

Do not compare results gathered with materially different workloads as though they were equivalent.

## End-to-end measurements still require a real desktop

For release performance characterization, use a macOS test machine and separately measure:

- CLI cold startup;
- daemon cold startup;
- idle resident memory;
- idle CPU over a sustained period;
- perception latency with OCR disabled/enabled;
- active-app detection latency;
- action-policy overhead;
- approved benign action latency;
- recipe end-to-end overhead;
- long-running memory/CPU drift.

Desktop measurements should include multiple runs and percentile distributions. Avoid describing an unmeasured code path as "instant", "zero latency", or a similar absolute claim.
