# guru10ms — saved working state, 2026-09-28

USRP-2945 (X310 + 2× TwinRX, 4 coherent channels) hopping **2.4 → 5.2 → 5.8 GHz**,
each band **10 ms switching (discarded) + 10 ms dwell (used)**, one cycle = 60 ms,
timed by the X310's own clock, with per-band phase correction and CALIBRATE.
Same code as git tag `guru10ms` (commit `d135177`) in `~/radar2`; that commit
makes `run_hop.sh` run the files in its own folder.

**How to run it:** see [RUN_GURU_FAST.md](RUN_GURU_FAST.md). In short:

```bash
cd ~/radar2/guru10ms
./install_blocks.sh      # only if the installed blocks differ (./RESTORE.sh --check says so)
./run_hop.sh --fast
```

Then press CALIBRATE. **How it works:** see the "guru_fast" section of [README.md](README.md).

## What is in here

| Path | What |
|---|---|
| `guru_fast.grc` / `guru_fast.py` | the 10 ms hopping flowgraph (open in GRC 3.8) |
| `guru.grc` / `guru.py` | the original guru (10 s host-timed hopping), kept for reference |
| `oot/` | block sources: `twinrx_radio_source` (radio-clock source), `hop_blocks` (band select, phase meter, tag rotator), `hop_calibrator`, `phase_correct_hopping`, their GRC `.yml` files |
| `oot/engine/` | C++ radio-clock engine `twinrx_engine.cpp` + `build.sh` (`install_blocks.sh` builds it) |
| `make_guru_fast.py` | builds `guru_fast.grc` from `guru.grc` (other bands, dwell, switching time) |
| `run_hop.sh` | starts the HackRF tone, then the receiver |
| `install_blocks.sh` | builds the engine and installs the blocks into `~/gnuradio-3.8` |
| `hackrf_tone_source.py` | lab transmitter (HackRF One, system GNU Radio 3.10, UDP control on 127.0.0.1:5123) |
| `phase_table_*.txt/.cfg` | startup phase table and the last CALIBRATE result |
| `dwell_exact_check.py`, `fast_chain_check.py`, `hop_blocks_selftest.py`, `gui_band_tour.py` | checks (see RUN_GURU_FAST.md §9) |
| `*_test.py` | the measurements behind the design (timed tune, tune speed, gr-uhd 180° flip, schedule) |
| `results/` | their measured results (JSON + pictures; raw `.npz` captures left out, 110 MB) |
| `installed_snapshot/` | exactly what was installed in `~/gnuradio-3.8` when saved: the `doa` Python package (incl. `_doa_swig.so`, `libtwinrx_engine.so`), GRC block files, `libgnuradio-doa.so` |
| `RESTORE.sh` | `--verify` (checksums), `--check` (installed vs this copy), no argument = reinstall the snapshot |
| `SHA256SUMS` | checksums of every file here |

## Measured on the hardware when saved

* Dwell 10,000 samples, switch 10,000, slot period 20,000 at 1 MS/s: 2,968 / 2,968 slots exact.
* 30 min GUI run: 90,005 of 90,008 slots used; 0 unlocked in over 100,000 slots.
* After CALIBRATE all bands within 1°. Restarts ≤ 0.55°. Thermal drift up to ~8° in 16 min → CALIBRATE every 5–10 min.

## Needs outside this folder

* GNU Radio 3.8 + UHD 3.15 at `~/gnuradio-3.8` (`source ~/gnuradio-3.8/setup_env.sh`), UHD headers at `~/uhd-3.15/include` (engine build).
* System GNU Radio 3.10 + gr-soapy for the HackRF.
