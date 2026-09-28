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
| Next step | waiting for the user's next instruction |

---

## 2026-09-28

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
