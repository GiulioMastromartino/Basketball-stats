# Production machine (perf reference)

All server-side benchmarks and release-wheel expectations for the
`Perf_Improvements` work should target this machine. Local macOS/ARM64
numbers are NOT representative (different arch, core count, and toolchains).

Host: Ubuntu Server, bare metal (not a VM). Docker runs natively.

## CPU

- Model: Intel(R) Core(TM) i5-4278U CPU @ 2.60GHz
- Count: 4 logical CPUs = 2 physical cores + Hyper-Threading
  (`lscpu`: `Thread(s) per core: 2`, `Core(s) per socket: 2`)
- Architecture: x86_64 (Haswell ULT, AVX2/FMA/BMI)
- Cache: 3 MB L3 (single instance)
- `CPU(s) scaling MHz: 70%` — sustained downclock under load

## Memory

- 7.6 GiB total — this is the hardware ceiling for a Macmini7,1
- ~774 MiB free, ~3.3 GiB buff/cache, **~959 MiB swap in use**
  (4 GiB `/swap.img`): the box runs under real memory pressure, so
  worker/replica count is a memory decision before it is a CPU one.

## Disk

- `sda` = `APPLE HDD HTS541` (2.5" 5400 rpm rotational, `ROTA=1`), 931 GB
- Root/PGDATA/Docker all share this single spindle: I/O wait is a
  co-equal bottleneck with CPU. Build and DB write bursts contend.

## Observed load

- `load average: 4.30 4.02 3.16` against 4 logical CPUs — the box is
  saturated in steady state, not idle.
- 16 containers plus a microk8s stack (`kubelite`, `k8s-dqlite`,
  `calico-node`) share the 2 physical cores.

## Implications for this repo

- Release wheels (`basketball_stats_rust`) must be built for x86_64;
  a local ARM64 `.so` is not transferable to prod.
- The Docker builder pins `RUSTFLAGS="-C target-cpu=haswell"` so LLVM
  can use AVX2/FMA. The resulting wheel requires Haswell-or-newer x86_64
  (fine: it only ever runs here); do not reuse it on older CPUs. Note the
  kernels are dominated by PyO3 extraction rather than floating-point
  work, so the AVX2 gain is unproven — benchmark `-C target-cpu=x86-64`
  against `haswell` before relying on it.
- **Rayon is NOT correctly sized by default here.** The pool is
  per-process, so 6 gunicorn processes x 4 threads = ~24 rayon threads
  on 4 logical CPUs, alongside Python threads, WeasyPrint render
  threads, Postgres and microk8s. Tune `RAYON_NUM_THREADS` explicitly
  (start at 2) rather than accepting the default.
- Because the box is saturated, replica/worker/thread counts
  (3 replicas x 2 workers x 2 threads) are the dominant latency factor,
  ahead of any Python- or Rust-level optimization.
- `.dockerignore` must exclude `basketball_stats_rust/target/`
  (~631 MB): copying it into the build context on a rotational disk
  costs real wall-clock on every build.
- Postgres runs with Docker's 64 MB `/dev/shm` default unless
  `shm_size` is set, which breaks parallel-query workers.
- The local macOS release build fails with `mis-aligned LINKEDIT`
  under rustc 1.96 + Xcode 26; build release artifacts on Linux
  (x86_64) instead.
- Re-run `bench_perf_improvements.py` on this hardware before claiming
  speedups. Note it runs single-threaded against in-memory SQLite, so
  it cannot observe CPU contention or Postgres behaviour — pair it with
  `vmstat 1`/`iostat -x` and the `flask_http_request_duration_seconds`
  percentiles already exported to Prometheus.
