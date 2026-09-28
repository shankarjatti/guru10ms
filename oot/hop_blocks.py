#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Blocks that follow twinrx_radio_source's sample-exact hop marks.

twinrx_radio_source stamps its first output stream with two tags, placed on
the exact samples computed from the radio clock:

  hop_off  (value: next band's frequency in Hz, or -1)
      from here the samples belong to a switch -- the guard before it and the
      settle after it -- and are not a measurement
  hop_on   (value: band frequency in Hz)
      from here until the next hop_off the samples are a dwell on that band

A slot that could not be scheduled safely, or whose LO lock was not
confirmed, gets no hop_on: it stays "off" and nothing downstream uses it.

Blocks here:
  hop_band_select   passes only the dwell samples of one chosen band
  hop_phase_meter   measures chN - ch0 per dwell window of one chosen band,
                    only where a tone is really present on every channel
"""
import math
import threading
import time

import numpy as np
import pmt
from gnuradio import gr

# Python blocks work on at least this many samples per call. Each call takes
# the GIL, and the radio scheduler thread needs it too; fewer, larger calls
# leave it more room. 4096 samples = 4 ms at 1 Msps.
CHUNK = 4096

TAG_OFF = "hop_off"
TAG_ON = "hop_on"
_K_OFF = pmt.intern(TAG_OFF)
_K_ON = pmt.intern(TAG_ON)


def hop_events(block, port, n):
    """(relative index, frequency or None) for hop tags in the next n items."""
    base = block.nitems_read(port)
    ev = []
    for t in block.get_tags_in_window(port, 0, n):
        if pmt.eq(t.key, _K_ON):
            ev.append((t.offset - base, float(pmt.to_double(t.value))))
        elif pmt.eq(t.key, _K_OFF):
            ev.append((t.offset - base, None))
    ev.sort(key=lambda e: e[0])
    # tags can arrive duplicated through multi-input blocks; keep one per offset
    out = []
    for e in ev:
        if out and out[-1][0] == e[0]:
            out[-1] = e
        else:
            out.append(e)
    return out


def segments(state, events, n):
    """Split [0, n) into (start, stop, band-or-None) runs; returns runs, new state."""
    runs = []
    pos = 0
    for idx, band in events:
        if idx > pos:
            runs.append((pos, idx, state))
        state = band
        pos = max(pos, idx)
    if pos < n:
        runs.append((pos, n, state))
    return runs, state


def same_band(a, b, tol=1e6):
    return a is not None and b is not None and abs(a - b) <= tol


class hop_band_select(gr.basic_block):
    """Pass only the dwell samples of one band; drop switching and other bands.

    frame_tag: if set, a tag with this key is put frame_offset samples after
    the start of every dwell window in the output. A time plot triggered on it
    always draws from inside one window, never across the join between two
    windows (the output is windows placed end to end).
    """

    def __init__(self, num_channels=4, band_freq=2.4e9, frame_tag="", frame_offset=100):
        gr.basic_block.__init__(self, name="Hop Band Select",
                                in_sig=[np.complex64] * num_channels,
                                out_sig=[np.complex64] * num_channels)
        self.set_tag_propagation_policy(gr.TPP_DONT)
        self.nch = int(num_channels)
        self.band_freq = float(band_freq)
        self._state = None
        self._frame_key = pmt.intern(frame_tag) if frame_tag else None
        self.frame_offset = int(frame_offset)
        self._active = False          # last output sample was inside a window
        self._pending = None          # samples left until this window's frame tag
        self.set_output_multiple(CHUNK)

    def set_band_freq(self, band_freq):
        self.band_freq = float(band_freq)

    def get_band_freq(self):
        return self.band_freq

    def forecast(self, noutput_items, ninput_items_required):
        for i in range(len(ninput_items_required)):
            ninput_items_required[i] = noutput_items

    def general_work(self, input_items, output_items):
        n = min(min(len(x) for x in input_items), len(output_items[0]))
        if n <= 0:
            return 0
        runs, self._state = segments(self._state, hop_events(self, 0, n), n)
        m = 0
        w0 = self.nitems_written(0)
        for a, b, band in runs:
            if not same_band(band, self.band_freq):
                self._active = False
                self._pending = None
                continue
            k = b - a
            if not self._active:
                self._active = True
                self._pending = self.frame_offset
            if self._frame_key is not None and self._pending is not None and self._pending < k:
                self.add_item_tag(0, w0 + m + self._pending, self._frame_key, pmt.PMT_T)
                self._pending = None
            elif self._pending is not None:
                self._pending -= k
            for c in range(self.nch):
                output_items[c][m:m + k] = input_items[c][a:b]
            m += k
        self.consume_each(n)
        return m


class hop_phase_meter(gr.basic_block):
    """Per-window chN - ch0 phase of one band, gated on a real tone.

    For every completed dwell window of the chosen band it checks, per
    channel, that a tone stands at least snr_min_db above the in-band noise
    floor (FFT over the window, peak vs median inside [f_lo, f_hi]). Only then
    does the window count. Output port c gives, once per window of the chosen
    band, the circular mean of chc - ch0 over the last avg_windows valid
    windows in degrees (port 0 is always 0), or NaN if there are none -- a
    readout never shows a number that was not measured on a real tone.

    Every report_s seconds it prints, for each band seen, how many windows
    there were, how many had a tone, the mean phase and the spread.
    """

    def __init__(self, num_channels=4, band_freq=2.4e9, samp_rate=1e6,
                 f_lo=60e3, f_hi=340e3, snr_min_db=20.0, avg_windows=10,
                 report_s=5.0):
        gr.basic_block.__init__(self, name="Hop Phase Meter",
                                in_sig=[np.complex64] * num_channels,
                                out_sig=[np.float32] * num_channels)
        self.set_tag_propagation_policy(gr.TPP_DONT)
        self.nch = int(num_channels)
        self.band_freq = float(band_freq)
        self.fs = float(samp_rate)
        self.f_lo, self.f_hi = float(f_lo), float(f_hi)
        self.snr_min_db = float(snr_min_db)
        self.avg_windows = int(avg_windows)
        self.report_s = float(report_s)
        self._state = None
        self._win = None            # list of per-call chunks while ON
        self._win_band = None
        self._queue = []            # rows to emit for the chosen band
        self._hist = {}             # band -> list of phase vectors (valid windows)
        self._stats = {}            # band -> counters
        self._lock = threading.Lock()
        self._t_report = time.time()
        self._t_emit = time.time()
        self.last_row = None          # last value put out (None before the first)

    def set_band_freq(self, band_freq):
        with self._lock:
            self.band_freq = float(band_freq)
            self._queue = []

    def get_stats(self):
        with self._lock:
            return {k: dict(v) for k, v in self._stats.items()}

    def recent(self, n=10):
        """Circular mean of chN - ch0 over the last n windows with a tone on
        this meter's band, or None if there are none."""
        with self._lock:
            h = []
            for k in self._hist:
                if same_band(k, self.band_freq):
                    h = list(self._hist[k][-int(n):])
        if not h:
            return None
        a = np.array(h)
        return np.degrees(np.angle(np.sum(np.exp(1j * np.radians(a)), axis=0))).tolist()

    def reset_band(self, band_freq):
        """Forget one band's history and counters (start of a calibration)."""
        with self._lock:
            for k in list(self._hist):
                if same_band(k, band_freq):
                    self._hist[k] = []
            for k in list(self._stats):
                if same_band(k, band_freq):
                    self._stats[k] = {"windows": 0, "tone": 0, "samples": 0}

    def band_summary(self, band_freq):
        """Windows seen, windows with a tone, and mean / std / max deviation
        (degrees, per channel pair) of chN - ch0 since the last reset_band."""
        with self._lock:
            h = []
            st = {"windows": 0, "tone": 0}
            for k in self._hist:
                if same_band(k, band_freq):
                    h = list(self._hist[k])
            for k in self._stats:
                if same_band(k, band_freq):
                    st = dict(self._stats[k])
        out = {"windows": st.get("windows", 0), "tone": st.get("tone", 0), "n": len(h)}
        if h:
            a = np.array(h)
            m = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(a)), axis=0)))
            d = (a - m[None] + 180.0) % 360.0 - 180.0
            out.update(mean=m.tolist(), std=d.std(axis=0).tolist(),
                       max_dev=np.abs(d).max(axis=0).tolist())
        return out

    def forecast(self, noutput_items, ninput_items_required):
        for i in range(len(ninput_items_required)):
            ninput_items_required[i] = CHUNK

    def _finish_window(self):
        chunks, band = self._win, self._win_band
        self._win, self._win_band = None, None
        if not chunks:
            return
        x = np.concatenate(chunks, axis=1)
        L = x.shape[1]
        st = self._stats.setdefault(band, {"windows": 0, "tone": 0, "samples": 0})
        st["windows"] += 1
        st["samples"] += L
        nan_row = [0.0] + [float("nan")] * (self.nch - 1)
        if L < 256:
            if same_band(band, self.band_freq):
                self._queue.append(nan_row)
            return
        w = np.hanning(L).astype(np.float32)
        F = np.fft.fftfreq(L, 1.0 / self.fs)
        inband = (F >= self.f_lo) & (F <= self.f_hi)
        snr = []
        for c in range(self.nch):
            S = np.abs(np.fft.fft(x[c] * w)) ** 2
            s = S[inband]
            snr.append(10 * np.log10(np.max(s) / (np.median(s) + 1e-30) + 1e-30))
        st["min_snr_db"] = float(min(min(snr), st.get("min_snr_db", 1e9)))
        if min(snr) < self.snr_min_db:
            if same_band(band, self.band_freq):
                self._queue.append(nan_row)
            return
        st["tone"] += 1
        C = np.sum(x[1:] * np.conj(x[0])[None], axis=1)
        ph = np.degrees(np.angle(C))
        h = self._hist.setdefault(band, [])
        h.append(ph)
        if len(h) > 1000:
            del h[:-1000]
        if same_band(band, self.band_freq):
            last = np.array(h[-self.avg_windows:])
            m = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(last)), axis=0)))
            self._queue.append([0.0] + list(m))

    def _report(self):
        now = time.time()
        if now - self._t_report < self.report_s:
            return
        self._t_report = now
        for band in sorted(self._stats):
            st = self._stats[band]
            h = np.array(self._hist.get(band, [])[-200:])
            if len(h):
                m = np.degrees(np.angle(np.sum(np.exp(1j * np.radians(h)), axis=0)))
                dev = np.max(np.abs((h - m + 180.0) % 360.0 - 180.0), axis=0)
                ph = "  ".join("ch%d %+7.2f (max dev %.2f)" % (c + 1, m[c], dev[c])
                               for c in range(len(m)))
            else:
                ph = "no tone"
            print("[meter] %.4f GHz  windows %d  with tone %d  worst SNR %.1f dB | %s"
                  % (band / 1e9, st["windows"], st["tone"], st.get("min_snr_db", float("nan")), ph))

    def general_work(self, input_items, output_items):
        n = min(len(x) for x in input_items)
        with self._lock:
            if n > 0:
                runs, self._state = segments(self._state, hop_events(self, 0, n), n)
                for a, b, band in runs:
                    if band is None:
                        if self._win is not None:
                            self._finish_window()
                        continue
                    if self._win is not None and not same_band(band, self._win_band):
                        self._finish_window()
                    if self._win is None:
                        self._win, self._win_band = [], band
                    self._win.append(np.array([input_items[c][a:b] for c in range(self.nch)]))
                self.consume_each(n)
            self._report()
            if not self._queue and time.time() - self._t_emit > 0.5:
                # nothing measured on the chosen band for 0.5 s: say so
                self._queue.append([0.0] + [float("nan")] * (self.nch - 1))
            k = min(len(self._queue), len(output_items[0]))
            if k:
                self._t_emit = time.time()
                self.last_row = list(self._queue[k - 1])
            for i in range(k):
                row = self._queue[i]
                for c in range(self.nch):
                    output_items[c][i] = row[c]
            del self._queue[:k]
        return k


class hop_tag_rotator(gr.sync_block):
    """Per-band phase correction switched on the hop tags, sample-exact.

    Channel 0 passes through, channel c is multiplied by exp(-j*offset_c) of
    the band named by the most recent hop_on. Between a hop_off and the next
    hop_on every output is zero: those samples are a switch, not a signal.
    table: [(freq_hz, [rad_ch1, rad_ch2, ...]), ...]
    """

    def __init__(self, num_channels, table, freq_tol=1e6):
        gr.sync_block.__init__(self, name="Hop Tag Rotator",
                               in_sig=[np.complex64] * num_channels,
                               out_sig=[np.complex64] * num_channels)
        self.nch = int(num_channels)
        self.freq_tol = float(freq_tol)
        self._state = None
        self._lock = threading.Lock()
        self._unknown = set()
        self.set_table(table)
        self.set_output_multiple(CHUNK)

    def set_table(self, table):
        with self._lock:
            self._table = [(float(f), np.exp(-1j * np.asarray(r, dtype=np.float64)).astype(np.complex64))
                           for f, r in table]

    def _rot(self, band):
        for f, rot in self._table:
            if abs(f - band) <= self.freq_tol:
                return rot
        if band not in self._unknown:
            self._unknown.add(band)
            print("[phasecal] NO ROW FOR %.4f GHz -- its dwell samples are passed "
                  "UNCORRECTED" % (band / 1e9))
        return None

    def work(self, input_items, output_items):
        n = len(output_items[0])
        with self._lock:
            runs, self._state = segments(self._state, hop_events(self, 0, n), n)
            for a, b, band in runs:
                if band is None:
                    for c in range(self.nch):
                        output_items[c][a:b] = 0
                    continue
                rot = self._rot(band)
                output_items[0][a:b] = input_items[0][a:b]
                for c in range(1, self.nch):
                    if rot is None:
                        output_items[c][a:b] = input_items[c][a:b]
                    else:
                        output_items[c][a:b] = input_items[c][a:b] * rot[c - 1]
        return n

