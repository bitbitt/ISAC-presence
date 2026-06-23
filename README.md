# OFDM-Based Bistatic ISAC Demonstrator (SDR)

A real-hardware demonstrator of **Integrated Sensing and Communication (ISAC)** — also known as **Joint Communication and Sensing (JCAS)** — built on a single OFDM waveform over software-defined radio. One transmission simultaneously carries data (communication) and senses the environment (human presence via forward-scatter), sharing the same waveform, hardware, and spectrum.

> **Scope (honest positioning).** This is an **ISAC Level-1 (coexistence), communication-centric, single-stream (SISO) bistatic** demonstrator. It proves sensing–communication coexistence and quantifies their trade-off on real hardware. It is **not** a full 6G ISAC system — there is no MIMO, beamforming, or angle/position estimation. It detects **presence** (someone crossing the link, at ≤ ~2 m for this setup), not location. The range/echo outputs are visualization context, **not** a detection claim. Implementation is **Python + UHD/SDR — not MATLAB**.

---

## What it is

| Aspect | Detail |
|---|---|
| Waveform | OFDM, single shared frame for comm + sensing (Nfft=64, frame=2320 samples) |
| Communication | QPSK payload (text + CRC), bistatic link |
| Sensing | Forward-scatter JCAS detector (LoS amplitude/phase, MAD-CFAR) → **presence detection** |
| Hardware | USRP B210 (TX) + LibreSDR (RX), 2× omni antennas, bistatic |
| RF | fs = 40 MS/s, fc = 5.9 GHz |
| Geometry | Bistatic (separate TX/RX), infrastructure-to-infrastructure style link |

ISAC is one of the six usage scenarios for 6G defined by ITU-R IMT-2030, where sensing and communication share one infrastructure. This project demonstrates the **coexistence layer** of that vision on accessible SDR hardware.

---

## How one waveform does both

OFDM splits the spectrum into many narrow, orthogonal subcarriers. "One waveform" does **not** mean one modulation — each subcarrier can carry its own. In one OFDM symbol (64-point FFT, ±25 active):

| Subcarrier group | Count | Modulation | Role |
|---|---|---|---|
| Centre (`k = ±1..±4`) | 8 | **QPSK** | communication payload ("STEI" + CRC) |
| Spread across the band | 38 | **BPSK** (known seq) | sensing reference (forward-scatter) |
| `k = ±7, ±21` | 4 | pilots (`1+0j`) | phase reference (CPE correction) |
| DC + `\|k\| ≥ 26` | — | null | guard band |

All groups are summed by **one IFFT** into a single time-domain frame. They stay separable because each subcarrier sits on a distinct, orthogonal frequency bin. QPSK (2 bits/SC) is compact, so 8 centre subcarriers suffice for the payload; BPSK is more robust, ideal for a stable sensing reference.

**Demodulation** reverses this with a shared front-end and a per-group decision rule:

1. **Sync** — STF (Schmidl–Cox) coarse + LTF matched-filter fine alignment.
2. **Channel estimate** — `H_est = Y_LTF / X_LTF` per subcarrier (averaged over 2 LTF symbols).
3. **Per data symbol** — FFT → one-tap equalize `Y_eq = Y / H_est` → pilot-driven CPE phase correction.
4. **Split by subcarrier index** — the FFT already separated the bins; only the decision rule differs: QPSK demap on the 8 comm subcarriers, BPSK hard-slice on the 38 sense subcarriers.

The sense subcarriers are *known*, so the receiver compares received vs. expected to extract the amplitude/phase perturbation — the forward-scatter sensing feature — from the **same frame** that carried the data.

---

## How the sensing works

The detector measures **forward-scatter**: a body crossing the line-of-sight (LoS) perturbs the received signal amplitude. Detection is amplitude-driven; the Doppler proxy is intentionally de-weighted because it is contaminated by carrier-frequency-offset (CFO) jitter.

Detection score (simplified):

```
score ≈ |amp_hp| / amp_sigma
        amp_hp    = amplitude deviation from a slow baseline   (window: ma_len   = 90)
        amp_sigma = robust spread of recent amplitude (MAD)    (window: cfar_len = 120)
```

A **presence state machine** holds an `OCCUPIED` state while the subject moves (bridging brief LoS gaps), returning to `EMPTY` only after a configurable silent period. The hold is now expressed **directly in frames** (`--sense-presence-frames`, default 200) — see *Lessons learned* for why this is frame-native rather than seconds-based.

---

## Key results (proof)

Measured on real hardware. Static = empty room; walk = person crossing the LoS. Walk dataset: distance sweep (1 / 2 / 3 m) × orientation (horizontal vs. side-of-RX) plus multi-subject path scenarios, 20 000 frames per run.

**Static (empty room, 3 runs):**

| Metric | Result |
|---|---|
| **False alarms** | **0 / 0 / 0** — steady-state score max **0.97 / 1.23 / 1.50** (threshold 2.5) |
| **Communication PRR** | **99.94 / 99.96 / 99.98 %** |

**Walk (presence) — hardware-validated:**

| Scenario | Detected frames /20k | Peak score | PRR (overall) | PRR (worst 100-frame window) |
|---|---|---|---|---|
| 1 m crossing | ~12.3k–13.9k | 8.9–11.3 | 99.1–99.6 % | 87 % |
| 2 m crossing | ~0.8k–5.3k | 3.2–5.0 | 99.6–99.9 % | — |
| 3 m crossing | **0** | 1.70–2.04 (< floor) | 99.7–99.8 % | — |
| Multi-subject / centre-LoS path | ~5.7k–7.3k | 8.8–21.1 | 96.8–98.8 % | **38–63 %** |

| Finding | Result |
|---|---|
| **Latch fix (state machine)** | **Confirmed on hardware** — every detecting run shows `ON → OFF` transitions (4–39 per run) and separate OCCUPIED segments (median ≈ hold window); the counter clears normally, **no latch** |
| **Detection range** | Robust at ≤ 1 m, present-but-orientation-sensitive at 2 m, **below the detection floor at 3 m** (peak score 1.70–2.04 < 2.5 → 0 detections). Effective forward-scatter presence range ≈ **≤ 2 m** for this setup/threshold |
| **ISAC trade-off** | When a body crosses the **centre** of the LoS, PRR collapses to **38–63 %** in the worst window and EVM swings from ~−11 dB (clean) to a **+5 dB** peak — a large, localized degradation *coincident with detection* |

**Core empirical finding:** communication degrades **precisely** when an object crosses the line-of-sight — the same physical event that triggers detection. This sensing–communication tension is the fundamental trade-off of ISAC, demonstrated here on real RF hardware rather than simulation.

> **Detection mechanism (no over-claim):** runs with and without a 5G handset are both detected equally well — sensing is **body forward-scatter (shadowing)**, *not* detection of the phone's 5G emission. The system senses a person, not a device.

> **Validation status:** static behaviour, the comm/sensing trade-off, and continuous-presence walk behaviour (OCCUPIED duration, `ON → OFF` clear, no latch) are now all **validated on hardware**. Remaining open item: per-frame timestamps to express the hold/OCCUPIED duration in seconds (currently reported in frames) — see Roadmap.

---

## What was learned

- **Doppler from phase-delta is unreliable under CFO drift.** A ~7–8 kHz CFO jitter contaminated the Doppler proxy, causing false detections in an empty room. Amplitude (forward-scatter shadowing) is the trustworthy feature; the fix was to de-weight Doppler and let amplitude dominate.
- **Detection-count is not a quality metric.** A good detector fires when an object is present and stays silent when the room is empty. Raw counts are dominated by *how the subject moves*, not by tuning.
- **The baseline can "swallow" a stationary target (self-masking).** Too short an adaptation window makes a paused person the new "normal." A longer baseline window mitigates this.
- **Two tuning knobs pull in opposite directions.** The baseline window (`ma_len`) raises the score numerator; the normalization window (`cfar_len`) suppresses it during motion (denominator). They must be balanced, not maximized.
- **The human variable dominates.** Run-to-run detection counts varied 2–4× purely from walking differently. Reproducible results need a standardized movement protocol.
- **PRR alone can hide problems.** Dropped frames (lost over USB) do not lower PRR but reduce throughput; both must be reported.
- **Forward-scatter sensing is range- and geometry-limited.** Detection is robust at ≤ 1 m, weaker and orientation-dependent at 2 m (a perpendicular crossing shadows the LoS far more than a path alongside the receiver), and falls **below the detection floor at 3 m** for this setup. Sensing coverage is a physical property of the link geometry and threshold, not a software limit.
- **The trade-off magnitude depends on the crossing geometry.** A fast single crossing barely dents PRR (worst window ~87 %); a slow body — or two — through the LoS *centre* collapses it to 38–63 %. The worst-case figure is what bounds a coexistence design, not the run average.
- **Express frame-counted timing in frames, not seconds.** A presence "timeout in seconds" was internally converted to frames using `fs / frame_length` (≈17,241/s) — the *theoretical* sample-to-frame rate, **not** the real per-frame processing cadence (~13–15 frames/s, limited by USB + demod). The mismatch silently over-sized the hold counter by ~1000×, producing a counter longer than the entire run that would latch `OCCUPIED` forever once triggered. The fix was to make the hold **frame-native** (deterministic, FPS-independent), now **confirmed on hardware** across 16 walk runs (clean `ON → OFF` clears, no latch). General lesson: *a hold/timeout counter must always be validated against the run length, and verified by execution rather than by reading a number.*

## What was gained

- A working, hardware-validated **ISAC Level-1 coexistence demonstrator** with a *quantified* sensing–communication trade-off (PRR 38–63 % in the worst window when the LoS is blocked).
- A **deterministic, frame-native presence state machine**, now **confirmed on hardware** (16 walk runs, clean `ON → OFF` clears, no latch).
- A characterized **detection envelope** for the link: robust ≤ 1 m, orientation-sensitive at 2 m, below floor at 3 m.
- An honest, defensible positioning of what a single bistatic SISO link can and cannot claim (presence, not position; a person, not a device).

---

## Usage

```bash
# Default parameters are tuned for the reference setup — bare run works:
python3 ofdm_isac_bistatic_isac_presence-f.py --phase1b --fs 40e6 --frames 5000 \
    --tx-gain 90 --rx-gain 76 --text "STEI" --log-csv run.csv
```

Key tunable flags (sensible defaults baked in):

| Flag | Default | Meaning |
|---|---|---|
| `--sense-ma-len` | 90 | baseline window (anti self-masking) |
| `--sense-cfar-len` | 120 | normalization / threshold window |
| `--sense-min-score` | 2.5 | detection floor |
| `--sense-presence-frames` | 200 | **presence hold, in frames** (frame-native, FPS-independent) |
| `--calib-frames` | 400 | clutter calibration (room must be still) |

**Important:** during calibration (first ~400 frames) the room must be still. For walk tests, wait for the `[CALIB] ... FASE DETEKSI mulai` message before moving.

A no-hardware AWGN self-test is available via `--simulate` (validates the comm chain without an SDR).

Output: per-frame CSV log (comm + range + JCAS columns). Detection flag in column `jcas_object_detected`.

---

## Roadmap

- [x] **Walk-presence hardware validation** — done. Across 16 walk runs, `jcas_object_detected` shows clean `ON → OFF` transitions (4–39 per detecting run); the latch fix holds end-to-end on hardware.
- [x] **Final dataset** — collected: 3× static + a distance sweep (1 / 2 / 3 m) × orientation (horizontal / side-of-RX) + multi-subject path scenarios.
- [ ] **Per-frame timestamps in the CSV** — measure the actual frame rate, so the frame-based hold and OCCUPIED duration can also be reported in seconds with confidence. (Still open; durations are currently expressed in frames.)
- [ ] **Extend range beyond 2 m** — lower `--sense-min-score` or raise RX gain; must re-verify static false-alarm rate (empty-room score max is 0.97–1.50, so a floor below ~2.0 starts to risk false alarms).
- [ ] **ISAC Level-2 (cooperation):** sensing-driven adaptive modulation (QPSK↔BPSK when an object blocks the LoS) — "sensing assists communication," the next step toward true ISAC co-design.
- [ ] Future direction: MIMO / multi-node for angle and position estimation (toward localization).

---

## Repository contents

| File | Purpose |
|---|---|
| `ofdm_isac_bistatic_isac_presence-f.py` | Main SDR ISAC implementation (Python / UHD) |
| `README.md` | This file |
| `CONTEXT_TRANSFER.md` | Internal working notes (tuning rationale, gotchas, workplan) |

---

## Notes

- Sensing claims are limited to **presence detection on a single bistatic link**. Range/echo outputs are visualization context, not detection claims. A single bistatic link gives presence + coarse range, **not** position (x, y) — there is no triangulation.
- This is a research demonstrator; parameters are tuned for the specific physical setup (antennas, room, gains). **Re-validate after changing the physical setup:** empty-room steady-state score max should stay below ~1.5 and walk above ~5 for the default threshold to hold.
