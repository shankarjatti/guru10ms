#!/usr/bin/env python3
"""Where does the lab tone really land on each band, and how close is it to 0 Hz?

The HackRF's frequency error (spec +/-20 ppm) scales with the RF frequency, so
a tone sent at centre + offset arrives at centre + offset + error, and on bands
whose LO plan inverts the spectrum at -(offset + error). With a small offset
(10 kHz) that can put the tone near, on, or across 0 Hz, where the receiver's
own DC offset and LO leakage sit -- those are steady and coherent, so a meter
that picks them up reports a phase with no tone at all. This measures it.

Per band: moves the HackRF there (UDP control, as guru does), tunes the four
TwinRX channels with the LO routing guru uses (ch2 exports, DDC 0 Hz), records
--secs of all four channels (no hopping, no timed commands) and reports, per
channel, the strongest peak outside +/- --dc-guard Hz, its level over the noise
median, the level of the 0 Hz bin, and the next strongest line (the HackRF's
own carrier leak sits at its centre, one offset away from the tone).

    source ~/gnuradio-3.8/setup_env.sh
    python3 tone_freq_check.py --offset 10e3            # HackRF started with --offset 10e3
"""
import argparse
import json
import os
import socket
import sys
import time

import numpy as np
import uhd

ap = argparse.ArgumentParser()
ap.add_argument("--addr", default="addr=192.168.10.2")
ap.add_argument("--rate", type=float, default=1e6)
ap.add_argument("--bands", default="2.4e9:46,5.2e9:60,5.8e9:69")
ap.add_argument("--offset", type=float, default=10e3, help="tone offset the HackRF was started with")
ap.add_argument("--secs", type=float, default=0.5)
ap.add_argument("--dc-guard", type=float, default=1e3, help="ignore |f| below this when looking for the tone")
ap.add_argument("--tx-control", default="127.0.0.1:5123")
ap.add_argument("--restore", type=float, default=2.4e9, help="band to leave the HackRF on")
a = ap.parse_args()
BANDS = [(float(f), float(g)) for f, g in (x.split(":") for x in a.bands.split(","))]
NCH = 4


def tx(cmd):
    host, port = a.tx_control.split(":")
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3.0)
    s.sendto(cmd.encode(), (host, int(port)))
    try:
        return s.recv(256).decode(errors="replace")
    finally:
        s.close()


u = uhd.usrp.MultiUSRP(a.addr)
u.set_rx_subdev_spec(uhd.usrp.SubdevSpec("A:0 A:1 B:0 B:1"), 0)
for ch, ant in enumerate(["RX1", "RX2", "RX1", "RX2"]):
    u.set_rx_antenna(ant, ch)
u.set_rx_rate(a.rate)
for ch in range(NCH):
    try:
        u.set_rx_lo_export_enabled(False, "all", ch)
    except Exception:
        pass
for ch, src in enumerate(["external", "external", "internal", "companion"]):
    u.set_rx_lo_source(src, "all", ch)
u.set_rx_lo_export_enabled(True, "all", 2)
sa =uhd.usrp.StreamArgs("fc32", "sc16")
sa.channels = list(range(NCH))
st = u.get_rx_stream(sa)
fs = u.get_rx_rate()
N = int(a.secs * fs)


def capture():
    buf = np.zeros((NCH, N), dtype=np.complex64)
    md = uhd.types.RXMetadata()
    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
    cmd.num_samps = N
    cmd.stream_now = False
    cmd.time_spec = u.get_time_now() + uhd.types.TimeSpec(0.1)
    st.issue_stream_cmd(cmd)
    got = 0
    tmp = np.zeros((NCH, 10000), dtype=np.complex64)
    while got < N:
        n = st.recv(tmp, md, 1.0)
        if md.error_code != uhd.types.RXMetadataErrorCode.none:
            raise RuntimeError("receive error: %s" % md.strerror())
        if n == 0:
            raise RuntimeError("receive timed out after %d of %d samples" % (got, N))
        k = min(n, N - got)
        buf[:, got:got + k] = tmp[:, :k]
        got += k
    return buf


rows = []
print("tone sent at centre %+.1f kHz; looking outside +/- %.1f kHz of 0 Hz" % (a.offset / 1e3, a.dc_guard / 1e3))
for f, gain in BANDS:
    print("\n== %.4f GHz  (HackRF: %s)" % (f / 1e9, tx("freq %d" % int(f)).strip()))
    treq = uhd.types.TuneRequest(f)
    treq.rf_freq = f
    treq.rf_freq_policy = uhd.types.TuneRequestPolicy.manual
    treq.dsp_freq = 0.0
    treq.dsp_freq_policy = uhd.types.TuneRequestPolicy.manual
    for _ in range(2):                         # twice, as every guru tune
        for ch in range(NCH):
            u.set_rx_gain(gain, ch)
            u.set_rx_freq(treq, ch)
    time.sleep(1.5)                            # LO lock + the HackRF's retune
    locked = u.get_rx_sensor("lo_locked", 2).to_bool()
    x = capture()
    w = np.hanning(N).astype(np.float32)
    F = np.fft.fftshift(np.fft.fftfreq(N, 1.0 / fs))
    res = F[1] - F[0]
    for ch in range(NCH):
        S = np.fft.fftshift(np.abs(np.fft.fft(x[ch] * w)) ** 2)
        med = np.median(S) + 1e-30
        away = np.abs(F) >= a.dc_guard
        i = int(np.argmax(np.where(away, S, 0)))
        dc = float(10 * np.log10(np.max(S[np.abs(F) < res * 3]) / med))
        # next line: strongest outside +/- 2 kHz of the tone and of 0 Hz
        mask = away & (np.abs(F - F[i]) > 2e3)
        j = int(np.argmax(np.where(mask, S, 0)))
        row = {"band": f, "ch": ch, "lo_locked": locked,
               "tone_hz": float(F[i]), "tone_db": float(10 * np.log10(S[i] / med)),
               "dc_db": dc, "next_hz": float(F[j]), "next_db": float(10 * np.log10(S[j] / med))}
        # every strong line, not just the biggest: tone, its mirror image and the
        # transmitter's carrier leak all sit within a few tens of kHz
        order = np.argsort(S)[::-1]
        lines = []
        for k in order:
            if len(lines) >= 6 or S[k] / med < 10 ** 2.0:
                break
            if all(abs(F[k] - F[q]) > 500 for q in lines):
                lines.append(int(k))
        row["lines"] = [(float(F[q]), float(10 * np.log10(S[q] / med))) for q in sorted(lines, key=lambda q: F[q])]
        rows.append(row)
        print("  ch%d  tone at %+9.1f Hz  %5.1f dB over noise | 0 Hz bin %5.1f dB | next line %+9.1f Hz %5.1f dB"
              % (ch, row["tone_hz"], row["tone_db"], dc, row["next_hz"], row["next_db"]))
        print("       lines: " + "  ".join("%+.0f Hz %.0f dB" % l for l in row["lines"]))
    t = np.median([r["tone_hz"] for r in rows if r["band"] == f])
    err = (abs(t) - a.offset) if abs(abs(t) - a.offset) < 200e3 else float("nan")
    print("  -> tone at %+.1f Hz (%s side); vs the %.1f kHz sent: %+.1f Hz = %+.2f ppm of %.2f GHz;  LO locked %s"
          % (t, "inverted" if t < 0 else "upright", a.offset / 1e3, err, err / f * 1e6, f / 1e9, locked))

print("\nHackRF back to %.2f GHz: %s" % (a.restore / 1e9, tx("freq %d" % int(a.restore)).strip()))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results",
                   "tone_freq_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
json.dump({"args": vars(a), "fs": fs, "rows": rows}, open(out, "w"), indent=1, default=str)
print("saved", out)
