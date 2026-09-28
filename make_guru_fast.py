#!/usr/bin/env python3
"""Build guru_fast.grc (radio-clock hopping, 10 ms dwell) from guru.grc.

guru.grc stays as it is -- the verified slow-hopping flowgraph. Changes:
  * source: schedule=radio, dwell 10 ms per band, settle 10 ms (0.25 ms guard
    before + 9.75 ms after each switch), tone parked on the displayed band
  * phase correction: follows the source's hop marks (sample-exact)
  * DC blockers removed from the signal path: their ~4 ms ringing after each
    switch would run past the guard; the band-pass already rejects DC
  * gates, the moving-average phase chain and the 50 ms band follow removed;
    Hop Band Select feeds the plot and spectrum, Hop Phase Meter the readouts
  * "Display band" chooser and a schedule status line

    python3 make_guru_fast.py && grcc guru_fast.grc -o .
    python3 make_guru_fast.py --bands 2.4e9:46,3.5e9:52,5.8e9:69 && grcc guru_fast.grc -o .

--bands  freq_hz:rx_gain_db,...  (1 to 4 bands; default: guru.grc's three).
A band's correction row comes from phase_table_deg.txt when that file has a
row for its frequency, otherwise from guru.grc, otherwise it is 0 and the
band is uncorrected until CALIBRATE is pressed -- this script says which.
"""
import argparse
import os
import sys

import yaml

SRC, OUT = "guru.grc", "guru_fast.grc"
TABLE = "phase_table_deg.txt"
FS = 1e6

ap = argparse.ArgumentParser()
ap.add_argument("--bands", default="", help="freq_hz:gain_db,... (1-4 bands)")
ap.add_argument("--dwell", type=float, default=0.010, help="dwell per band, s")
ap.add_argument("--settle", type=float, default=0.010, help="switching time per slot, s")
ap.add_argument("--guard", type=float, default=0.00025, help="part of it before each switch, s")
a = ap.parse_args()

g = yaml.safe_load(open(SRC))
blocks = {b["name"]: b for b in g["blocks"]}

hs0 = blocks["twinrx_hopping_source_0"]["parameters"]
if a.bands:
    BANDLIST = []
    for item in a.bands.split(","):
        f, gain = item.split(":")
        BANDLIST.append((float(f), float(gain)))
else:
    BANDLIST = [(float(hs0["freq_%d" % i]), float(hs0["gain_%d" % i]))
                for i in range(int(hs0["num_bands"]))]
problems = []
if not 1 <= len(BANDLIST) <= 4:
    problems.append("1 to 4 bands, got %d" % len(BANDLIST))
for f, gain in BANDLIST:
    if not 10e6 <= f <= 6e9:
        problems.append("%.4f GHz is outside the TwinRX range (10 MHz - 6 GHz)" % (f / 1e9))
    if 5.00e9 <= f <= 5.14e9:
        problems.append("%.4f GHz: this TwinRX cannot retune into 5.00-5.14 GHz "
                        "(LO1 never locks there, measured 2026-09-23)" % (f / 1e9))
for name, v in (("dwell", a.dwell), ("settle", a.settle), ("guard", a.guard)):
    if abs(v * FS - round(v * FS)) > 1e-6:
        problems.append("%s %.6f s is not a whole number of samples" % (name, v))
if not 0 <= a.guard < a.settle:
    problems.append("guard must be shorter than the switching time")
if problems:
    sys.exit("make_guru_fast: " + "; ".join(problems))
DWELL, SETTLE, GUARD = repr(a.dwell), repr(a.settle), repr(a.guard)

# correction rows: measured table first, then guru.grc, else uncorrected
measured = {}
if os.path.exists(TABLE):
    for line in open(TABLE):
        line = line.split("#", 1)[0].strip()
        if line:
            v = [float(x) for x in line.replace(",", " ").split()]
            measured[v[0]] = v[1:4]
pc0 = blocks["phase_correct_hopping_0"]["parameters"]
grc_rows = {}
for i in range(int(pc0["num_bands"])):
    grc_rows[float(pc0["freq_%d" % i])] = [float(x) for x in pc0["deg_%d" % i].strip("() ").split(",")]
ROWS = []
for f, _ in BANDLIST:
    m = [v for k, v in measured.items() if abs(k - f) <= 1e6]
    gr_ = [v for k, v in grc_rows.items() if abs(k - f) <= 1e6]
    if m:
        ROWS.append((f, m[0], TABLE))
    elif gr_:
        ROWS.append((f, gr_[0], SRC))
    else:
        ROWS.append((f, [0.0, 0.0, 0.0], None))
for f, d, where in ROWS:
    print("band %.4f GHz: correction %s %s" % (
        f / 1e9, "(%+.2f, %+.2f, %+.2f) deg" % tuple(d),
        "from %s" % where if where else "NONE -- UNCALIBRATED, press CALIBRATE before trusting it"))


def state(coord):
    return {"alias": "", "bus_sink": False, "bus_source": False, "bus_structure": None,
            "coordinate": list(coord), "rotation": 0, "state": "enabled"}


def add(name, bid, params, coord):
    b = {"name": name, "id": bid, "parameters": params, "states": state(coord)}
    g["blocks"].append(b)
    blocks[name] = b


remove = [f"dcblock_{i}" for i in range(4)] + [f"spec_gate_{i}" for i in range(4)] + \
         [f"disp_gate_{i}" for i in range(4)] + ["ph_est"] + \
         [f"ph_deg_{s}" for s in ("0", "1", "2", "2_0")] + \
         [f"ph_avg_{s}" for s in ("0", "1", "2", "2_0")] + \
         [f"ph_dec_{s}" for s in ("0", "1", "2", "2_0")]
g["blocks"] = [b for b in g["blocks"] if b["name"] not in remove]
g["connections"] = [c for c in g["connections"] if c[0] not in remove and c[2] not in remove]

g["options"]["parameters"]["id"] = "guru_fast"
g["options"]["parameters"]["title"] = "Guru fast: USRP-2945 4-Channel, 10 ms radio-clock hopping"

# --- source: the radio-clock source (pyuhd), replacing the gr-uhd one -------
hs = blocks["twinrx_hopping_source_0"]["parameters"]
g["blocks"] = [b for b in g["blocks"] if b["name"] != "twinrx_hopping_source_0"]
g["connections"] = [c for c in g["connections"]
                    if "twinrx_hopping_source_0" not in (c[0], c[2])]
add("twinrx_radio_source_0", "twinrx_radio_source", {
    "samp_rate": "samp_rate", "addresses": "'addr=192.168.10.2'", "num_bands": str(len(BANDLIST)),
    "settle": SETTLE, "guard_pre": GUARD, "gain_trim": hs["gain_trim"],
    "hop_enable": "True", "start_delay": "0.5", "tx_control": hs["tx_control"],
    "park_freq": "tone_band", "lock_check": "0.007", "min_slack": "0.008",
    "recv_buff_size": "33554432",
    **{k: v for i in range(4) for k, v in (
        ("freq_%d" % i, repr(BANDLIST[i][0]) if i < len(BANDLIST) else "1.0e9"),
        ("gain_%d" % i, repr(BANDLIST[i][1]) if i < len(BANDLIST) else "46"),
        ("dwell_%d" % i, DWELL))},
    "comment": "Hops on the X310 clock; hop_off/hop_on marks on the exact samples"},
    tuple(blocks["uhd_usrp_source_0"]["states"]["coordinate"]) if "uhd_usrp_source_0" in blocks else (8, 600))
SRC_NAME = "twinrx_radio_source_0"

# --- phase correction ----------------------------------------------------
pc0["follow_tags"] = "True"
pc0["num_bands"] = str(len(ROWS))
for i, (f, d, _) in enumerate(ROWS):
    pc0["freq_%d" % i] = repr(f)
    pc0["deg_%d" % i] = "(%.2f, %.2f, %.2f)" % tuple(d)

# --- lab tone band (HackRF) -------------------------------------------------
# Only moves the lab transmitter. The display never follows it: every band
# has its own panel, so the tone's band shows a signal and the others are flat.
opts = {}
for i in range(5):
    if i < len(BANDLIST):
        opts["option%d" % i] = repr(BANDLIST[i][0])
        opts["label%d" % i] = "%g GHz" % (BANDLIST[i][0] / 1e9)
    else:
        opts["option%d" % i] = str(i)
        opts["label%d" % i] = ""
add("tone_band", "variable_qtgui_chooser", dict({
    "comment": "", "gui_hint": "tabs@0:1,0,1,%d" % len(BANDLIST),
    "label": "LAB TONE (HackRF) BAND", "type": "real", "num_opts": str(len(BANDLIST)),
    "value": repr(BANDLIST[0][0]), "widget": "combo_box", "orient": "Qt.QHBoxLayout",
    "options": "[0, 1, 2]", "labels": "[]"}, **opts), (8, 440))
add("sched_state", "variable_qtgui_label", {
    "comment": "", "gui_hint": "tabs@0:2,0,1,%d" % len(BANDLIST), "label": "SCHEDULE",
    "type": "string", "value": "'starting'", "formatter": "None"}, (8, 520))
blocks["stream_state"]["parameters"]["gui_hint"] = "tabs@0:3,0,1,%d" % len(BANDLIST)
blocks["center_freq"]["parameters"]["value"] = "tone_band"
# the old single-band display, the gain slider (it controls nothing here) and
# the "displayed band" label go; per-band panels replace them
drop = ["gain", "band", "qtgui_time_sink_x_1"] + [f"time_resamp_{n}" for n in range(4)] + \
       [f"c2r_{n}" for n in range(4)]
TS_TEMPLATE = dict(blocks["qtgui_time_sink_x_1"]["parameters"])
RS_TEMPLATE = dict(blocks["time_resamp_0"]["parameters"])
NUM_TEMPLATE = dict(blocks["ph_num_1"]["parameters"])
g["blocks"] = [b for b in g["blocks"] if b["name"] not in drop]
g["connections"] = [c for c in g["connections"] if c[0] not in drop and c[2] not in drop]
for d in drop:
    blocks.pop(d, None)

add("spec_sel", "hop_band_select", {"num_channels": "4", "band_freq": "tone_band",
                                     "frame_tag": "''", "frame_offset": "100",
                                     "comment": "Spectrum: dwell samples of the lab tone's band"},
    (600, 60))

C = g["connections"]
# source out n -> bp (the old dcblock mapping, minus the dcblock)
for n, m in enumerate([0, 2, 3, 1]):
    C.append([SRC_NAME, str(n), f"bp_{m}", "0"])
# spectrum: source out n -> spec_sel n -> freq sink n
for n in range(4):
    C.append([SRC_NAME, str(n), "spec_sel", str(n)])
    C.append(["spec_sel", str(n), "qtgui_freq_sink_x_0", str(n)])

# --- per band: a phase meter only (numbers + SIGNAL/FLAT go in text lines) --
for i, (f, _) in enumerate(BANDLIST):
    x0 = 1400 + 900 * i
    tag = "%g GHz" % (f / 1e9)
    add(f"met_{i}", "hop_phase_meter", {
        "num_channels": "4", "band_freq": repr(f), "samp_rate": "samp_rate",
        "f_lo": "tone_offset - disp_bw/2 + 10e3", "f_hi": "tone_offset + disp_bw/2 - 10e3",
        "snr_min_db": "20", "avg_windows": "10", "report_s": "5",
        "comment": "chN - ch0 per %s dwell window, NaN when flat" % tag}, (x0, 1200))
    for n in range(4):
        C.append(["phase_correct_hopping_0", str(n), f"met_{i}", str(n)])
        add(f"met_{i}_null{n}", "blocks_null_sink", {"type": "float", "vlen": "1", "num_inputs": "1",
            "bus_structure_sink": "[[0,],]", "comment": ""}, (x0 + 300, 1150 + 40 * n))
        C.append([f"met_{i}", str(n), f"met_{i}_null{n}", "0"])

# --- main tab: sine waveforms of the lab tone's band + the phase readouts, as in guru
add("wave_sel", "hop_band_select", {"num_channels": "4", "band_freq": "tone_band",
    "frame_tag": "'hop_frame'", "frame_offset": "100",
    "comment": "dwell samples of the lab tone's band"}, (1400, 600))
wave = dict(TS_TEMPLATE)
wave.update(gui_hint="tabs@0:7,0,1,%d" % len(BANDLIST), tr_mode="qtgui.TRIG_MODE_TAG", tr_tag="'hop_frame'",
            tr_chan="0", tr_delay="0", entags="False",
            name='"RF waveforms of the LAB TONE band (its 10 ms dwells only), all 4 channels"')
add("wave_sink", "qtgui_time_sink_x", wave, (2000, 700))
for n in range(4):
    add(f"wave_rs_{n}", "rational_resampler_xxx", dict(RS_TEMPLATE), (1600, 600 + 60 * n))
    add(f"wave_c2r_{n}", "blocks_complex_to_real", {"vlen": "1", "comment": ""}, (1800, 600 + 60 * n))
    C.append(["phase_correct_hopping_0", str(n), "wave_sel", str(n)])
    C.append(["wave_sel", str(n), f"wave_rs_{n}", "0"])
    C.append([f"wave_rs_{n}", "0", f"wave_c2r_{n}", "0"])
    C.append([f"wave_c2r_{n}", "0", "wave_sink", str(n)])
add("ph_meter", "hop_phase_meter", {
    "num_channels": "4", "band_freq": "tone_band", "samp_rate": "samp_rate",
    "f_lo": "tone_offset - disp_bw/2 + 10e3", "f_hi": "tone_offset + disp_bw/2 - 10e3",
    "snr_min_db": "20", "avg_windows": "10", "report_s": "1e9",
    "comment": "readouts: chN - ch0 of the band shown above, NaN when flat"}, (1600, 1400))
# GNU Radio 3.8's number sink draws NaN as 0.000000 -- a phase that was never
# measured. The readouts are Qt labels instead (see the GUI snippet), fed from
# ph_meter.last_row, which say NO TONE when there is nothing to measure.
for sink in ["ph_num_0", "ph_num_1", "ph_num_2", "ph_num_2_0"]:
    g["blocks"] = [b for b in g["blocks"] if b["name"] != sink]
    C[:] = [c for c in C if sink not in (c[0], c[2])]      # in place: C is g["connections"]
    blocks.pop(sink, None)
for n in range(4):
    C.append(["phase_correct_hopping_0", str(n), "ph_meter", str(n)])
    add(f"ph_meter_null{n}", "blocks_null_sink", {"type": "float", "vlen": "1", "num_inputs": "1",
        "bus_structure_sink": "[[0,],]", "comment": ""}, (1900, 1400 + 40 * n))
    C.append(["ph_meter", str(n), f"ph_meter_null{n}", "0"])

# --- main plot: one whole cycle, every band, as the radio sees it -----------
# |x| of each corrected channel, averaged and decimated 20x (50 kHz), plotted
# over one full cycle and triggered on the source's hop_cycle mark, so the
# picture stands still: the tone's band shows its dwell, the others are flat,
# every switch shows as a zeroed gap.
ENV_DEC = 20
cyc_s = len(BANDLIST) * (a.settle + a.dwell)
blocks["tabs"]["parameters"]["num_tabs"] = "3"
blocks["tabs"]["parameters"]["label0"] = "Hopping"
blocks["tabs"]["parameters"]["label2"] = "Switching"
edges = []
t = 0.0
for f, _ in BANDLIST:
    edges.append("%g-%g ms switch | %g-%g ms %g GHz" % (t * 1e3, (t + a.settle) * 1e3,
                 (t + a.settle) * 1e3, (t + a.settle + a.dwell) * 1e3, f / 1e9))
    t += a.settle + a.dwell
sw = dict(TS_TEMPLATE)
sw.update(name='"One cycle:  %s"' % "  |  ".join(edges),
          gui_hint="tabs@2:0,0,1,%d" % len(BANDLIST), srate=repr(FS / ENV_DEC),
          size=str(int(round(cyc_s * FS / ENV_DEC))), ymin="-0.05", ymax="0.5",
          ylabel="|amplitude|", tr_mode="qtgui.TRIG_MODE_TAG", tr_tag="'hop_cycle'",
          tr_chan="0", tr_delay="0", entags="False", update_time="0.20")
add("sw_sink", "qtgui_time_sink_x", sw, (2400, 1600))
for n in range(4):
    add(f"sw_mag_{n}", "blocks_complex_to_mag", {"vlen": "1", "comment": ""}, (1900, 1600 + 60 * n))
    add(f"sw_avg_{n}", "blocks_moving_average_xx", {"type": "float", "length": str(ENV_DEC),
        "scale": "disp_gain * 1.0/%d" % ENV_DEC, "max_iter": "4000", "vlen": "1",
        "comment": "same display gain as the RF waveform plot"},
        (2050, 1600 + 60 * n))
    add(f"sw_dec_{n}", "blocks_keep_one_in_n", {"type": "float", "n": str(ENV_DEC), "vlen": "1",
        "comment": ""}, (2250, 1600 + 60 * n))
    C.append(["phase_correct_hopping_0", str(n), f"sw_mag_{n}", "0"])
    C.append([f"sw_mag_{n}", "0", f"sw_avg_{n}", "0"])
    C.append([f"sw_avg_{n}", "0", f"sw_dec_{n}", "0"])
    C.append([f"sw_dec_{n}", "0", "sw_sink", str(n)])


# --- stop: the source stops its own scheduler inside the flowgraph stop -----
blocks["snippet_lo_stop"]["parameters"]["code"] = """# twinrx_radio_source stops its scheduler and the stream inside the
# flowgraph's own stop, before the device goes away. Only the GUI poll is
# left to stop here.
self._hop_run = False
for _t in ("_follow_timer", "_now_timer", "_now_timer_ph"):
    try:
        getattr(self, _t).stop()
    except Exception:
        pass
self._twinrx_run = False
"""

# --- GUI poll (replaces the 50 ms band follow) -----------------------------
blocks["snippet_hop"]["parameters"]["code"] = '''# Radio-clock hopping: the band changes every 20 ms on the radio's own clock,
# far faster than a GUI can follow, so nothing here touches the band. The
# correction, the plot and the readouts all switch on the hop marks the
# source puts on the exact samples. This only reports status, twice a second.
from PyQt5 import QtCore

self._hop_run = True
self._fast_state = {}

def _poll():
    st = self._fast_state
    src = self.twinrx_radio_source_0
    try:
        s = src.get_schedule_stats()
        alive = src.stream_is_alive()
        stalls = src.get_stream_stalls()
    except Exception as e:
        s, alive, stalls = None, None, 0
        if not st.get('err'):
            st['err'] = True
            print('[follow] cannot read the source: %s: %s' % (type(e).__name__, e))
    if s is not None:
        txt = ('slots %d | used %d | late %d | unlocked %d | skipped %d | too slow %d | '
               'send: typical %.1f ms, worst %.1f ms (limit @@LIMIT@@ ms)'
               % (s['slots'], s['valid'], s['late'], s['unlocked'], s['skipped'],
                  s['unknown_in_time'], s.get('avg_send_ms', 0.0), s['max_send_ms']))
        if s['timing_lost']:
            txt = 'TIMING LOST - restart. ' + txt
        if txt != st.get('sched'):
            st['sched'] = txt
            self.set_sched_state(txt)
    state = ('receiving' if alive else
             'UNKNOWN - cannot read the stream state' if alive is None else
             'STOPPED - the radio is not sending, nothing below is a reading')
    if stalls:
        state += '   (recovered %d time(s) this run)' % stalls
    if state != st.get('stream'):
        st['stream'] = state
        self.set_stream_state(state)

# CALIBRATE: re-measure the table on the live chain (lab tone), see
# doa/hop_calibrator.py. Result is applied only if every band passes.
import os
import doa
from PyQt5 import Qt as _Qt
self._cal = doa.hop_calibrator(
    self.twinrx_radio_source_0, self.phase_correct_hopping_0, @@METERS@@,
    @@BANDS@@, secs=4.0,
    out_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'phase_table_live_deg.txt'))
self._cal_btn = _Qt.QPushButton('CALIBRATE  (lab tone on each band, ~15 s)')
self._cal_lbl = _Qt.QLabel('CAL: startup table from the flowgraph (not re-measured this session)')
def _cal_click():
    if self._cal.start(restore_freq=self.tone_band):
        self._cal_btn.setEnabled(False)
self._cal_btn.clicked.connect(_cal_click)
self.tabs_grid_layout_0.addWidget(self._cal_btn, 0, 0, 1, 1)
self.tabs_grid_layout_0.addWidget(self._cal_lbl, 0, 1, 1, @@NB1@@)

# one status line per band: SIGNAL or FLAT, from that band's own dwells
self._band_lbl = []
for _i, (_f, _m) in enumerate(@@BANDMETERS@@):
    _l = _Qt.QLabel('%g GHz: waiting for dwells' % (_f / 1e9))
    _l.setStyleSheet('font-family: monospace; font-size: 13pt;')
    self.tabs_grid_layout_2.addWidget(_l, 1 + _i, 0, 1, @@NB@@)
    self._band_lbl.append((_f, _m, _l, {'w': 0, 't': 0}))

self._now_lbl = _Qt.QLabel('RECEIVING NOW: starting')
self._now_lbl.setStyleSheet('font-size: 15pt; font-weight: bold;')
self.tabs_grid_layout_0.addWidget(self._now_lbl, 4, 0, 1, @@NB@@)
self._lock_lbl = _Qt.QLabel('LO LOCK: starting')
self._lock_lbl.setStyleSheet('font-size: 12pt;')
self.tabs_grid_layout_0.addWidget(self._lock_lbl, 5, 0, 1, @@NB@@)
self._show_lbl = _Qt.QLabel('SHOWING: starting')
self._show_lbl.setStyleSheet('font-size: 13pt; font-weight: bold; color: #1a4d8f;')
self.tabs_grid_layout_0.addWidget(self._show_lbl, 6, 0, 1, @@NB@@)

def _lock_poll():
    bs = self.twinrx_radio_source_0.get_band_lock_stats()
    parts = []
    for _f in @@BANDS@@:
        b = [v for k, v in bs.items() if abs(k - _f) <= 1e6]
        if not b:
            parts.append('%g GHz: waiting' % (_f / 1e9))
            continue
        b = b[0]
        bad = b['unlocked'] + b['late'] + b['skipped']
        parts.append('%g GHz: locked %d/%d%s' % (_f / 1e9, b['locked'], b['slots'],
                     '' if not bad else '  (%d NOT used)' % bad))
    self._lock_lbl.setText('LO LOCK (confirmed before every dwell):   ' + '   |   '.join(parts))
    tb = float(self.tone_band)
    b = [v for k, v in bs.items() if abs(k - tb) <= 1e6]
    ok = bool(b) and b[0]['slots'] > 0 and b[0]['locked'] == b[0]['slots']
    lock_txt = ('LO LOCKED on every dwell' if ok else
                'LO lock NOT confirmed on every dwell (those dwells are not drawn)')
    # is the lab tone actually there? (the receiver can be perfect while the
    # transmitter is silent -- say which one it is)
    ms = self.ph_meter.get_stats()
    row = [v for k, v in ms.items() if abs(k - tb) <= 1e6]
    w, t = (row[0]['windows'], row[0]['tone']) if row else (0, 0)
    last = self._fast_state.setdefault('tone_seen', {'w': 0, 't': 0, 'band': tb})
    if last['band'] != tb:
        last.update(w=w, t=t, band=tb)
    dw, dt = w - last['w'], t - last['t']
    last['w'], last['t'] = w, t
    if dw > 0 and dt == 0:
        self._show_lbl.setStyleSheet('font-size: 13pt; font-weight: bold; color: #c00000;')
        self._show_lbl.setText('SHOWING:  %g GHz  --  NO TONE right now (0/%d dwells): the lab '
                               'transmitter is not sending on this band. Receiver OK: %s'
                               % (tb / 1e9, dw, lock_txt))
    else:
        self._show_lbl.setStyleSheet('font-size: 13pt; font-weight: bold; color: #1a4d8f;')
        self._show_lbl.setText('SHOWING:  %g GHz  (LAB TONE band) -- its 10 ms dwells only, %s%s'
                               % (tb / 1e9, lock_txt,
                                  '' if dw <= 0 or dt == dw else
                                  '  -- tone in only %d/%d dwells' % (dt, dw)))

self._ph_val = []
for _c in range(4):
    _t = _Qt.QLabel('ch%d - ch0 phase offset (deg)' % _c)
    _t.setStyleSheet('font-size: 13pt; font-weight: bold;')
    _v = _Qt.QLabel('waiting')
    _v.setStyleSheet('font-family: monospace; font-size: 15pt;')
    self.tabs_grid_layout_0.addWidget(_t, 8 + _c, 0, 1, 1)
    self.tabs_grid_layout_0.addWidget(_v, 8 + _c, 1, 1, @@NB1@@)
    self._ph_val.append(_v)

def _ph_poll():
    row = self.ph_meter.last_row
    for _c, _v in enumerate(self._ph_val):
        if row is None:
            _v.setText('waiting for the first dwell')
            _v.setStyleSheet('font-family: monospace; font-size: 15pt; color: gray;')
        elif _c == 0:
            _v.setText('   0.000 deg  (reference)')
            _v.setStyleSheet('font-family: monospace; font-size: 15pt;')
        elif row[_c] != row[_c]:
            _v.setText('NO TONE - nothing measured')
            _v.setStyleSheet('font-family: monospace; font-size: 15pt; color: #c00000; font-weight: bold;')
        else:
            _v.setText('%+8.3f deg   (average of the last 10 dwells)' % row[_c])
            _v.setStyleSheet('font-family: monospace; font-size: 15pt;')

def _now_poll():
    st, f = self.twinrx_radio_source_0.get_current()
    if f:
        self._now_lbl.setText('RECEIVING NOW:  %g GHz  (%s)' % (f / 1e9, st))
self._now_timer = QtCore.QTimer(self)
self._now_timer.timeout.connect(_now_poll)
self._now_timer.start(40)

def _band_poll():
    for _f, _m, _l, _last in self._band_lbl:
        _s = _m.get_stats()
        _row = [v for k, v in _s.items() if abs(k - _f) <= 1e6]
        _w = _row[0]['windows'] if _row else 0
        _t = _row[0]['tone'] if _row else 0
        dw, dt = _w - _last['w'], _t - _last['t']
        _last['w'], _last['t'] = _w, _t
        _ph = _m.recent(10)
        _num = ('  '.join('ch%d-ch0 %+7.2f deg' % (c + 1, v) for c, v in enumerate(_ph))
                if _ph is not None and dt > 0 else '  '.join('ch%d-ch0     nan    ' % (c + 1) for c in range(3)))
        if dw <= 0:
            _state = 'NO DWELLS ARRIVING   '
        elif dt == dw:
            _state = 'SIGNAL (%2d/%2d dwells)' % (dt, dw)
        elif dt == 0:
            _state = 'FLAT   ( 0/%2d dwells)' % dw
        else:
            _state = 'PARTLY (%2d/%2d dwells)' % (dt, dw)
        _l.setText('%-8s  %s   %s' % ('%g GHz' % (_f / 1e9), _state, _num))

def _cal_poll():
    if self._cal.status != self._fast_state.get('cal'):
        self._fast_state['cal'] = self._cal.status
        if self._cal.status != 'not run':
            self._cal_lbl.setText('CAL: ' + self._cal.status)
    self._cal_btn.setEnabled(not self._cal.busy)

self._follow_timer = QtCore.QTimer(self)
self._follow_timer.timeout.connect(_poll)
self._follow_timer.timeout.connect(_cal_poll)
self._follow_timer.timeout.connect(_band_poll)
self._follow_timer.timeout.connect(_lock_poll)
self._now_timer_ph = QtCore.QTimer(self)
self._now_timer_ph.timeout.connect(_ph_poll)
self._now_timer_ph.start(200)
self._follow_timer.start(500)
'''

blocks["snippet_hop"]["parameters"]["code"] = blocks["snippet_hop"]["parameters"]["code"].replace(
    "@@BANDS@@", repr([f for f, _ in BANDLIST])).replace(
    "@@METERS@@", "{%s}" % ", ".join("%r: self.met_%d" % (f, i) for i, (f, _) in enumerate(BANDLIST))).replace(
    "@@BANDMETERS@@", "[%s]" % ", ".join("(%r, self.met_%d)" % (f, i) for i, (f, _) in enumerate(BANDLIST))).replace(
    "@@NB1@@", str(max(1, len(BANDLIST) - 1))).replace(
    "@@NB@@", str(len(BANDLIST))).replace(
    "@@LIMIT@@", "%g" % round((a.settle + a.dwell - 0.007) * 1e3, 3))

yaml.safe_dump(g, open(OUT, "w"), default_flow_style=False, sort_keys=False, width=100)
print("wrote %s: %d blocks, %d connections" % (OUT, len(g["blocks"]), len(g["connections"])))
