# WORK LOG — live

Updated at **every stage** of the work, so nothing is lost when a session is compacted
or restarted. Newest entry first. The finished story is in [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md);
hardware facts are in [lab_notes/](lab_notes/README.md).

**Rule for each entry:** date + time, what was asked (user's words where it matters),
what was done, what was measured (numbers, file in `results/`), what failed and why,
decisions taken, and what comes next. Only measured facts; anything not verified is marked so.

---

## CURRENT STATE (keep this block up to date)

| | |
|---|---|
| Working system | guru_fast — 2.4 → 5.2 → 5.8 GHz, 10 ms switch + 10 ms dwell, 60 ms cycle, radio clock |
| Code on the lab PC | `~/radar2/guru10ms/` (this repo, pushed) and `~/radar2/guru/` (same code; lab git repo `~/radar2`, tag `guru10ms` = `d135177`) |
| GitHub | https://github.com/shankarjatti/guru10ms (public, branch `main`) |
| Backups | `~/radar2/guru10ms.tar.gz`, `~/radar2/BACKUP_FAST_2026-09-28/` (+ `.tar.gz`), `~/radar2/BACKUP_WORKING_2026-09-28/` (10 s guru) |
| Run | `./run_hop.sh --fast`, then CALIBRATE; every 5–10 min for < 1° |
| Radio | X310 `31082D8` at 192.168.10.2; HackRF tone on 2.4 GHz (UDP 127.0.0.1:5123) |
| Open items | thermal drift (~8°/16 min); rtprio not enabled (limit 0); CPU governor = `powersave` (not yet tested as a cause of late slots); field calibration without HackRF; overflow recovery untested; RTOS choice |
| Next step | switching < 5 ms: ping-pong LO test (`pingpong_test.py`, to write): switch time, phase of all 4 channels vs current method, spare-LO lock in time, spurs |

---

## 2026-09-28

### 19:10 — user: "we are working with shared LO ... all LOs should be synchronized"
* Ping-pong keeps the shared-LO rule: at every instant **all 4 channels use one and the same synthesiser**
  (ch0/ch1 `external` via the cable, ch2/ch3 on board B, export follows ch2's source). The spare synthesiser
  feeds no channel while it tunes; at the hop all 4 channels move to it together.
* The two synthesisers never serve at the same time, so they do not need to be phase-locked to each other;
  both run from the same reference clock. The inter-channel phase (chN − ch0) is what is measured, and the
  common LO phase cancels in it.
* What changes: the LO reaches each channel by a slightly different path from synth A (ch2's) than from
  synth B (ch3's) → a phase table per (band, synth): with 3 bands and 2 synths the pattern repeats every
  6 dwells → 6 table rows, CALIBRATE measures all 6.
* Must be verified in the test: each (band, synth) state repeats its phase; no 180° states; the spare
  synth's retuning does not leak into the active LO (spurs / phase disturbance during the dwell).

### 19:00 — user: switching must be below 5 ms — is it possible by code?
* Answer: **not by making the retune faster** (the ~5.4–5.8 ms is the TwinRX synthesiser itself: ADF5355
  VCO auto-calibration + PLL lock, plus the SPI writes at 3 MHz, all executed in the radio's command queue —
  UHD source `adf535x.cpp` waits `_wait_time_us` during autocal).
* **Yes by a different method: ping-pong LOs** — Ettus's own `host/examples/twinrx_freq_hopping.cpp`
  (default hop interval 5 ms): while one LO set receives, the spare LO set is tuned to the next band; at the
  hop only the LO **source switch** flips (`internal` ↔ `companion`).
* Our mapping: board B has two LO sets (ch2's, currently exported, and ch3's, currently idle because ch3 is
  `companion`). UHD source `twinrx_experts.cpp` l.333–345: the exported LO **follows** the exporting
  channel's source (ch2 `companion` → exports ch3's synth), so board A (`external`) follows the flip and all
  4 channels stay on one LO.
* Unknown until measured: switch time after the flip; whether the phase repeats (the 180° / wrong-state
  problem of a single timed tune may come back); whether the spare LO locks within dwell + switch
  (5 ms + 1 ms = 6 ms vs lock 5.4–5.84 ms single pass, 2nd pass unknown) → dwell 5 ms is at the edge;
  spurs from the spare synth retuning during a dwell.

### 18:45 — user: move to 5 ms, solve the open problems during that work
* User: "we need to move 1 more step like 5ms ... during that time only we'll solve these problems also".
* Facts that decide 5 ms (measured): LO lock after a **single** timed tune = 5.40–5.84 ms after T
  (`timed_tune_20260928_122715.json`, 300 hops). Our phase-correct method adds a 2nd pass at S+3 ms;
  its lock time has never been measured on its own (only "locked at S+7 ms" in > 100,000 slots).
* So: **5 ms dwell is possible; 5 ms switching is not** with this tune (the LO is still unlocked at 5 ms).
* The PC's time per slot shrinks (lock read at S+7 ms, next batch must be sent before the next S):
  10/10 → 13 ms; 5 dwell/10 switch → 8 ms (worst send seen with GUI ~9 ms). So the real-time
  settings (problem A) become required, not optional — they get solved inside the 5 ms work.
* Plan: (1) measure lock time of the exact method → shortest safe switch; (2) rtprio + CPU performance;
  (3) 5 ms dwell with that switch: exact-sample check, then 30-min GUI soak, target 0 dropped;
  (4) drift + automatic recovery along the way. guru10ms stays untouched; work in `~/radar2/guru`,
  save as `guru5ms` when verified.

### 18:35 — requirement: receiver side 100 % correct
* User: "for testing only we are using hack rf ... i need receiver side should be 100% correct".
* Already true by design and measured: a dwell is used only if its band, LO lock and exact timing are
  confirmed; everything else is discarded and counted. **No wrong number is ever shown.**
* Not yet 100 %: (A) dropped dwells, 3 / 90,008 in the 30-min GUI soak (Linux late); (B) phase accuracy
  between calibrations (drift up to ~8° / 16 min, receiver LO cable A↔B); (C) no automatic recovery
  after lost samples (untested).
* Plan proposed: Stage 1 timing (rtprio 95 + CPU `performance`, engine threads pinned to own cores;
  target 0 dropped in 30 min). Stage 2 automatic resync after sample loss, tested by forcing a stall.
  Stage 3 one-hour drift log with a fixed table → calibration interval from numbers; phase-stable LO
  cable as the permanent fix (software cannot make a cable's thermal drift zero).

### 18:25 — work log started
* User: "every time keep updating things on .md file ... some time we need to compact the session".
* Created this file. From now on every stage is written here as it happens, committed and pushed
  to `guru10ms`.

### 18:20 — repo pushed to GitHub
* User gave https://github.com/shankarjatti/guru10ms: "every small information should be there ... every related file".
* Repo was empty and **public**; asked the user — answer: **push as public**.
* Added: raw `.npz` results (110 MB) + `results/README.md` (every run with its own verdict),
  `docs/DEVELOPMENT_LOG.md`, `docs/lab_notes/`, lab git history, `third_party/gr-doa` source + patch vs
  upstream `7f982b7`, `environment/` (versions, network, `uhd_usrp_probe`), `earlier_work/lo_sharing/`,
  `logs/`, landing `README.md`.
* Checked before push: no secrets (grep for tokens/keys/passwords), 0 broken links, 366 files in SHA256SUMS.
* Pushed 2 commits (`45c7579`, `35a5bfe`). Fresh clone from GitHub: all 366 files intact.
  GitHub warned on one 85 MB file (limit is 100 MB) — uploaded complete.
* Found: `results/sched_10on_10off_20260928_122954.json` is incomplete (numpy-bool JSON bug); marked so.
* Left out on purpose: `guru2/3/4`, `guru_phase`, `guru_doa`, `gururaj` (older/stale), `BACKUP_*` (duplicates).

### 18:10 — safe copy `guru10ms` made
* User: "KEEP THIS WORK SAFE MAKE A COPY OF IT AND NAME IT AS A guru10ms".
* `run_hop.sh` changed to run the files in its own folder (commit `d135177`, tag `guru10ms` in `~/radar2`);
  from `~/radar2/guru` behaviour is unchanged.
* `~/radar2/guru10ms/`: project + `installed_snapshot/` + `RESTORE.sh` + `SHA256SUMS`.
* Verified: installed blocks = copy; engine rebuilt from the copy is byte-identical to the installed one;
  `hop_blocks_selftest.py` passed; `guru_fast.grc` regenerates the same `guru_fast.py`.

### Before 18:00 — guru_fast built and verified
* See [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) §3–§5 (stages 1–14, all measurements, all fixes).
