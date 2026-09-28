#!/usr/bin/env python3
"""Calibrate / verify guru_fast's phase table through guru_fast's own chain.

Same blocks and settings as guru_fast.grc, no GUI:
  twinrx_radio_source (radio-clock hopping, 10 ms on / 10 ms off, 3 bands)
    -> complex band-pass (disp_taps_bp) -> phase_correct_hopping (follow_tags)
    -> hop_phase_meter
The receiver hops all three bands the whole time; the HackRF tone is parked on
one band at a time, so each band is measured while the others are hopped past.

  --calibrate           correction table all zero -> the measured chN - ch0 IS
                        the table; written to --out
  --table FILE          apply this table -> the result is the residual

Each band reports: dwell windows with a tone, circular mean, spread (std) and
largest deviation of a single 10 ms window from the mean.

    python3 fast_chain_check.py --calibrate --secs 20 --out phase_table_deg.txt
    python3 fast_chain_check.py --table phase_table_deg.txt --secs 20
"""
import argparse
import json
import os
import time

import numpy as np
from gnuradio import gr, blocks, filter
from gnuradio.filter import firdes

import doa

BANDS = [(2400000000, 46, 0.01), (5200000000, 60, 0.01), (5800000000, 69, 0.01)]
TONE_OFFSET, DISP_BW, FS = 200e3, 300e3, 1e6


def read_table(path):
    rows = {}
    for line in open(path):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        v = [float(x) for x in line.replace(",", " ").split()]
        rows[v[0]] = v[1:4]
    return rows


def wrap(d):
    return (np.asarray(d) + 180.0) % 360.0 - 180.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--table", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--secs", type=float, default=20.0, help="per band")
    ap.add_argument("--bands", default="", help="comma list of band freqs to park on (default all)")
    a = ap.parse_args()
    if a.calibrate == bool(a.table):
        raise SystemExit("give exactly one of --calibrate or --table FILE")
    table = {f: [0.0, 0.0, 0.0] for f, _, _ in BANDS}
    if a.table:
        t = read_table(a.table)
        for f in table:
            if f not in t:
                raise SystemExit("%s has no row for %.4f GHz" % (a.table, f / 1e9))
            table[f] = t[f]

    src = doa.twinrx_radio_source(
        samp_rate=FS, addresses="addr=192.168.10.2",
        bands=[(f, g, d) for f, g, d in BANDS], settle=0.01, guard_pre=0.00025,
        gain_trim=(0.0, -13.3, 1.5, -1.7), hop_enable=True, start_delay=0.5,
        tx_control="127.0.0.1:5123", park_freq=BANDS[0][0], lock_check=0.007,
        min_slack=0.008)
    taps = firdes.complex_band_pass(1.0, FS, TONE_OFFSET - DISP_BW / 2,
                                    TONE_OFFSET + DISP_BW / 2, DISP_BW / 4,
                                    firdes.WIN_HAMMING)
    corr = doa.phase_correct_hopping(
        num_channels=4, bands=[(f, tuple(table[f]), 10) for f, _, _ in BANDS],
        cal_file="", follow_source=True, settle=1.0, start_delay=2.0,
        freq_tol=1000000, follow_tags=True)
    meter = doa.hop_phase_meter(4, BANDS[0][0], FS, TONE_OFFSET - DISP_BW / 2 + 10e3,
                                TONE_OFFSET + DISP_BW / 2 - 10e3, 20, 10, 1e9)
    tb = gr.top_block()
    for c in range(4):
        bp = filter.fir_filter_ccc(1, taps)
        tb.connect((src, c), bp, (corr, c))
        tb.connect((corr, c), (meter, c))
        tb.connect((meter, c), blocks.null_sink(gr.sizeof_float))
    tb.start()
    time.sleep(2.0)

    res = {}
    try:
        parks = [float(x) for x in a.bands.split(",")] if a.bands else [b[0] for b in BANDS]
        for f, _, _ in BANDS:
            if float(f) not in parks:
                continue
            src.set_park_freq(f)
            meter.set_band_freq(f)
            time.sleep(1.0)                          # tone settles on the new band
            with meter._lock:
                meter._hist[float(f)] = []
                st0 = dict(meter._stats.get(float(f), {"windows": 0, "tone": 0}))
            time.sleep(a.secs)
            with meter._lock:
                h = np.array(meter._hist.get(float(f), []))
                st1 = dict(meter._stats.get(float(f), {"windows": 0, "tone": 0}))
            res[f] = (h, st1["windows"] - st0.get("windows", 0), st1["tone"] - st0.get("tone", 0))
    finally:
        sched = src.get_schedule_stats()
        tb.stop()
        tb.wait()

    mode = "CALIBRATE (no correction)" if a.calibrate else "VERIFY with %s" % a.table
    print("\n=== %s ===" % mode)
    print("scheduler: %s" % sched)
    rows = []
    ok = True
    report = {"mode": mode, "sched": sched, "bands": {}}
    np.savez(os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                          "fast_chain_hist_%s.npz" % time.strftime("%Y%m%d_%H%M%S")),
             **{"b%d" % int(f / 1e6): res[f][0] for f in res})
    for f, _, _ in BANDS:
        if f not in res:
            continue
        h, nwin, ntone = res[f]
        if not len(h):
            print("%.1f GHz: NO WINDOWS WITH A TONE (%d windows seen)" % (f / 1e9, nwin))
            ok = False
            continue
        m = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(h)), axis=0)))
        d = wrap(h - m[None])
        sd, mx = d.std(axis=0), np.abs(d).max(axis=0)
        print("%.1f GHz: %d/%d dwell windows with tone | mean chN-ch0: %8.3f %8.3f %8.3f deg"
              " | std %.3f %.3f %.3f | worst window %.3f %.3f %.3f"
              % (f / 1e9, ntone, nwin, *m, *sd, *mx))
        report["bands"][str(f)] = {"n": int(len(h)), "windows": nwin, "mean": m.tolist(),
                                   "std": sd.tolist(), "max_dev": mx.tolist()}
        rows.append((f, m))
        if not a.calibrate and (np.abs(m).max() >= 1.0 or mx.max() >= 1.0):
            ok = False
    if a.calibrate and a.out and len(rows) == len(BANDS):
        with open(a.out, "w") as fh:
            fh.write("# Measured (chN - ch0) in DEGREES through guru_fast's own chain:\n"
                     "# radio-clock hopping 10 ms on / 10 ms off, gains 46/60/69,\n"
                     "# gain_trim (0.0, -13.3, 1.5, -1.7), LO exported by board B.\n"
                     "# %s. Valid for THIS power session only.\n"
                     "# freq_hz, ch1_deg, ch2_deg, ch3_deg\n" % time.strftime("%Y-%m-%d %H:%M"))
            for f, m in rows:
                fh.write("%d, %.4f, %.4f, %.4f\n" % (f, *m))
        print("table written to %s" % a.out)
    if not a.calibrate:
        print("RESULT: %s" % ("ALL BANDS WITHIN 1 DEG" if ok else "NOT WITHIN 1 DEG ON EVERY BAND"))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "fast_chain_%s_%s.json" % (
            "cal" if a.calibrate else "verify", time.strftime("%Y%m%d_%H%M%S"))), "w") as fh:
        json.dump(report, fh, indent=1)


if __name__ == "__main__":
    main()
