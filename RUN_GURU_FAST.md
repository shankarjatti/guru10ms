# guru_fast — how to run it

USRP-2945 (X310 + 2× TwinRX) hopping **2.4 → 5.2 → 5.8 GHz**, each band
**10 ms OFF (switching, LO relocks, discarded) + 10 ms ON (dwell, used)**,
one cycle = **60 ms**, timed by the X310's own clock. HackRF One = lab tone.

## 1. Before you start

* X310 powered, Ethernet on `enp3s0` (192.168.10.1 ↔ X310 192.168.10.2), 1 GigE.
* LO cables between the two TwinRX boards in place (board B exports the LO).
* HackRF One on USB, its output through the splitter into all 4 RX ports.
* **After an X310 power cycle the phase table is invalid** — press CALIBRATE (step 4).

## 2. First time only (or after changing any block code)

```bash
cd ~/radar2/guru10ms
./install_blocks.sh
```

Builds the C++ engine (`oot/engine/twinrx_engine.cpp` → `libtwinrx_engine.so`)
and installs every block into `~/gnuradio-3.8`. Close guru first.

## 3. Start

```bash
cd ~/radar2/guru10ms
./run_hop.sh --fast
```

This starts the HackRF tone (on 2.4 GHz) first, then `guru_fast.py`.
Logs: `/tmp/guru_rx.log` (receiver), `/tmp/hackrf_tone.log` (transmitter).
Restart everything cleanly: `./run_hop.sh --fast --restart`.
Stop: close the window (never `kill -9`).

## 4. Calibrate

Press **CALIBRATE** (top left). For ~15 s the HackRF visits 2.4, 5.2 and 5.8 GHz,
each band's offsets are measured on its own 10 ms dwells, and the HackRF goes
back to the LAB TONE band. The new table is applied **only if every band
passes** (≥ 50 dwells, a tone in every dwell, spread < 0.3°, no dwell > 1° off);
the line next to the button says `OK ...` or `REJECTED ...` and why.

**When:** after every start, and every **5–10 minutes** if you need < 1°.
Measured today: restarts are stable (two starts ≤ 0.55°), but the offsets drift
with temperature — up to ~8° in 16 min this afternoon on the board-A↔B pairs.

## 5. What you see

**Hopping tab (main)** — like the original guru screen, plus the hopping status

| Item | Meaning |
|---|---|
| LAB TONE (HackRF) BAND | where the HackRF transmits. Default **2.4 GHz only**; it is never retuned unless you change this or press CALIBRATE. |
| SCHEDULE | slots / used / late / unlocked / skipped, typical and worst send time vs the limit (13 ms) |
| STREAM | `receiving`, or `STOPPED` / `TIMING LOST` (then nothing is a reading) |
| RECEIVING NOW | band being received now, and whether it is switching or in its 10 ms dwell |
| LO LOCK | per band: dwells with the LO lock confirmed / all dwells (a dwell without confirmed lock is never used) |
| SHOWING | which band the plot shows (the LAB TONE band) and that its LO was locked. In **red** if that band has **no tone** (the transmitter is not sending there) — the receiver is still fine. |
| RF waveforms plot | sine waves of the LAB TONE band's 10 ms dwells, all 4 channels |
| chN − ch0 phase offset (deg) | average of the last 10 dwells of that band; **NO TONE – nothing measured** when there is no tone (never a made-up 0.000) |

**Switching tab** — one plot of the whole 60 ms cycle:
0–10 ms switch, **10–20 ms 2.4 GHz**, 20–30 switch, **30–40 ms 5.2 GHz**, 40–50 switch,
**50–60 ms 5.8 GHz**. With the HackRF on 2.4 GHz only the 10–20 ms window has a signal;
the other dwells are **flat**. Under it one line per band: `SIGNAL` + phases, or `FLAT` + `nan`.

**Spectra tab** — spectrum of the LAB TONE band's dwells.

If the plot goes flat for a few seconds while LO LOCK stays full, the HackRF's
own transmit stream stalled and its watchdog is restarting it (see
`/tmp/hackrf_tone.log`, lines `[watchdog] ...`). That is the transmitter, not the
receiver. The tone script no longer retunes onto the frequency it is already on
(retuning is what makes the HackRF stall) and recovers a stall in ~2-3 s.

## 6. Safety rules built in

* A slot that is late, skipped or not locked is **never used** (counted in SCHEDULE).
* Lost samples → `TIMING LOST`, all dwells stop being used; restart.
* No tone on a band → `nan`, never an old or made-up number.

## 7. Optional: real-time priority (fewer "late" slots)

Once (then log out and in):

```bash
echo "shankar - rtprio 95" | sudo tee /etc/security/limits.d/99-sdr-rt.conf
```

Then set **Real-time priority = 90** in the *TwinRX Radio-Clock Hopping Source*
block (GRC → guru_fast.grc) and regenerate (step 8).

## 8. Editing the flowgraph

* Open in GNU Radio Companion 3.8: `~/gnuradio-3.8/run_grc.sh ~/radar2/guru10ms/guru_fast.grc`
* After saving: `cd ~/radar2/guru10ms && source ~/gnuradio-3.8/setup_env.sh && grcc guru_fast.grc -o .`
* Different bands: `python3 make_guru_fast.py --bands 2.4e9:46,5.2e9:60,5.8e9:69` then
  `grcc guru_fast.grc -o .` (1–4 bands; 5.00–5.14 GHz is refused — LO1 cannot lock there).
  `make_guru_fast.py` rebuilds guru_fast.grc from guru.grc, so edits made only in
  guru_fast.grc are lost if you run it.

## 9. Checks you can run (radio free, guru closed)

```bash
python3 dwell_exact_check.py --secs 60      # every dwell/switch/slot = exact sample count
python3 fast_chain_check.py --table phase_table_deg.txt --secs 20   # all bands within 1 deg?
python3 hop_blocks_selftest.py              # block logic, no radio
```

## 10. Back to a known-good state

```bash
~/radar2/guru10ms/RESTORE.sh --check
~/radar2/guru10ms/RESTORE.sh
```
