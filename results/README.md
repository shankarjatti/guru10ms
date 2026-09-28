# results/ -- every measurement from 2026-09-28

Each test writes `<test>_<date>_<time>.json` (summary + per-hop data); some also write a `_blocks.npz`
(raw sample blocks) or `_hist.npz` (per-dwell phase history). `gui_*.png` are window pictures taken by
`gui_band_tour.py` (`tab0` = Hopping tab, `tab2` = Switching tab). **Failed runs are kept** with their own
verdicts: they are how each problem was found.

## Test types

* `tune_speed` -- how fast one band change is: gain/tune call times, LO drop and lock after the due time (tune_speed_test.py)
* `dwell_50ms` -- host-timed dwell test, 50 ms (dwell_test.py)
* `dwell_10ms` -- host-timed dwell test, 10 ms (dwell_test.py)
* `timed_tune` -- timed tune: when lo_locked goes True after the command time T (timed_tune_test.py)
* `tune_method` -- phase of single timed tune vs staggered + 2nd pass vs guru host double tune (tune_method_phase_test.py)
* `sched_10on_10off` -- radio-clock scheduled 10 ms on / 10 ms off, Python scheduler (sched_hop_test.py)
* `grc_timing` -- hop tags vs signal edges inside a GNU Radio flowgraph (grc_timing_test.py)
* `fast_chain_cal` -- full guru_fast chain without GUI, CALIBRATE mode (fast_chain_check.py --calibrate)
* `fast_chain_verify` -- full guru_fast chain without GUI, fixed table, residual per band (fast_chain_check.py --table)

## Every run (verdict as written by the test itself)

| run | result |
|---|---|
| `dwell_10ms_20260928_121745` | DWELL 10 ms: ACHIEVED |
| `dwell_50ms_20260928_120910` | DWELL 50 ms: NOT ACHIEVED -- 4 hop(s) not locked at end of settle; stream errors/gaps; stream rate 500003; 2.4 GHz: 60 visit(s) not steady; 5.2 GHz: 60 visit(s) not steady; 5.8 GHz: 59 visit(s) not steady |
| `dwell_50ms_20260928_121159` | DWELL 50 ms: NOT ACHIEVED -- 1 hop(s) not locked at end of settle; first packet time does not match the commanded start |
| `fast_chain_cal_20260928_132406` | slots 3211, used 3205, skipped 2, late 0, unlocked 0, worst send 10.5 ms |
| `fast_chain_cal_20260928_132526` | slots 1609, used 1608, skipped 0, late 0, unlocked 0, worst send 11.9 ms |
| `fast_chain_cal_20260928_144816` | slots 1617, used 1616, skipped 1, late 0, unlocked 0, worst send 6.9 ms |
| `fast_chain_cal_20260928_145036` | slots 4720, used 4719, skipped 1, late 0, unlocked 0, worst send 10.4 ms |
| `fast_chain_cal_20260928_152657` | slots 3219, used 3219, skipped 0, late 0, unlocked 0, worst send 5.7 ms |
| `fast_chain_verify_20260928_145236` | slots 4720, used 4716, skipped 4, late 0, unlocked 0, worst send 6.9 ms |
| `fast_chain_verify_20260928_152430` | slots 4720, used 4720, skipped 0, late 0, unlocked 0, worst send 6.5 ms |
| `fast_chain_verify_20260928_170028` | slots 1717, used 1717, skipped 0, late 0, unlocked 0, worst send 7.0 ms |
| `fast_chain_verify_20260928_170109` | slots 1717, used 1717, skipped 0, late 0, unlocked 0, worst send 7.6 ms |
| `grc_timing_20260928_125819` | see file |
| `sched_10on_10off_20260928_122954` | **file incomplete** -- the run hit the numpy-bool JSON bug while writing (fixed afterwards); no result |
| `sched_10on_10off_20260928_123019` | SCHEDULED HOPPING 10 ms ON / 10 ms OFF: NOT ACHIEVED -- 180 LATE command(s); 111 slot(s) without lock |
| `sched_10on_10off_20260928_123618` | SCHEDULED HOPPING 10 ms ON / 10 ms OFF (50% duty on every slot): ACHIEVED |
| `sched_10on_10off_20260928_123718` | SCHEDULED HOPPING 10 ms ON / 10 ms OFF (50% duty on every slot): ACHIEVED |
| `sched_10on_10off_20260928_124803` | SCHEDULED HOPPING 10 ms ON / 10 ms OFF: NOT ACHIEVED -- 5 LATE command(s); 1 slot(s) without lock; 2.4 GHz: 1 visit(s) not steady; 2.4 GHz: settles after the guard; 2.4 GHz: disturbed before the guard |
| `sched_10on_10off_20260928_132659` | SCHEDULED HOPPING 10 ms ON / 10 ms OFF (50% duty on every slot): ACHIEVED |
| `sched_10on_10off_20260928_132717` | SCHEDULED HOPPING 10 ms ON / 10 ms OFF (50% duty on every slot): ACHIEVED |
| `sched_10on_10off_20260928_152514` | SCHEDULED HOPPING 10 ms ON / 10 ms OFF (50% duty on every slot): ACHIEVED |
| `timed_tune_20260928_122432` | 30 hops, lock 5.41-5.76 ms after T |
| `timed_tune_20260928_122715` | 270 hops, lock 5.40-5.84 ms after T |
| `tune_method_20260928_123438` | see file |
| `tune_speed_20260928_120232` | see file |
| `tune_speed_20260928_120426` | see file |
| `tune_speed_20260928_120634` | see file |

Notes:
* `dwell_50ms_*` failed on the test's own bugs (half sample rate, 2x packet timestamps), fixed before `dwell_10ms`.
* `sched_*_123019` (180 late, 111 without lock) was the first 10/10 attempt; after the fixes the next runs (`123618`, `123718`) achieved it.
* `sched_*_124803` (5 late in 3,333 cycles = 10,000 slots) is the long soak that made the rule: a late slot is never used.
* `fast_chain_*` up to 14:52 used the Python scheduler; from 15:24 the C++ engine (0 skipped/late).
