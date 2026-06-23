#!/usr/bin/env python3
"""
analyze_pilar_ab.py  --  HW1 (komunikasi) pilar (a) & (b) extractor.

Dipakai SETELAH dua run hardware selesai:
  - baseline_T5_cold.csv   (per-frame, dari --log-csv)   -> pilar (a) stabilitas + warm-up
  - fs_sweep.csv           (ringkasan per-fs, dari --output-csv) -> pilar (b) bandwidth ceiling

Auto-deteksi tipe file dari kolom (fs_mhz => sweep, frame_idx => per-frame).
Stdlib saja, tidak butuh numpy. Output siap copy ke Bab IV.

  python3 analyze_pilar_ab.py baseline_T5_cold.csv
  python3 analyze_pilar_ab.py fs_sweep.csv
  python3 analyze_pilar_ab.py baseline_T5_cold.csv fs_sweep.csv --warmup 500
"""
import csv, sys, math, argparse

def _f(x):
    try: return float(x)
    except: return None

def _is_ok(v):
    return str(v).strip() in ("1", "1.0", "True", "true")

def mean_sd(xs):
    xs = [x for x in xs if x is not None]
    if not xs: return (float("nan"), float("nan"), 0)
    m = sum(xs)/len(xs)
    if len(xs) < 2: return (m, 0.0, len(xs))
    var = sum((x-m)**2 for x in xs)/(len(xs)-1)
    return (m, math.sqrt(var), len(xs))

# ---------- pilar (a) + warm-up : per-frame baseline ----------
def analyze_baseline(path, warmup):
    rows = list(csv.DictReader(open(path)))
    n = len(rows)
    if n == 0:
        print(f"[{path}] kosong."); return
    warmup = min(warmup, n//2)

    head = rows[:warmup]
    tail = rows[warmup:]

    # --- steady-state (ekor) : stabilitas pilar (a) ---
    evm_db   = [_f(r.get("comm_evm_db")) for r in tail]
    cfo      = [_f(r.get("cfo_hz"))      for r in tail]
    amp      = [_f(r.get("amp"))         for r in tail]
    prr = 100.0 * sum(1 for r in tail if _is_ok(r.get("crc_ok"))) / max(1, len(tail))

    evm_lin = [10**(e/20.0) for e in evm_db if e is not None]   # EVM linear utk CV yang sah
    em, es, _   = mean_sd(evm_db)
    elm, els, _ = mean_sd(evm_lin)
    cm, cs, _   = mean_sd([abs(c) for c in cfo if c is not None])
    am, asd, _  = mean_sd(amp)
    cv_evm = 100.0*els/elm if elm else float("nan")
    cv_amp = 100.0*asd/am  if am  else float("nan")

    # --- OVF steady-state rate (kolom ovf = COUNTER KUMULATIF, lesson 8.1) ---
    ovf_series = [_f(r.get("ovf")) for r in rows]
    ovf_series = [o for o in ovf_series if o is not None]
    ovf_rate = float("nan")
    if len(ovf_series) > warmup:
        d_ovf = ovf_series[-1] - ovf_series[warmup]
        ovf_rate = 100.0 * d_ovf / max(1, (len(ovf_series)-warmup))

    # --- warm-up transient (kepala) : pilar (b) kondisi awal ---
    nbin = 10
    binsz = max(1, warmup//nbin)
    print(f"\n=== {path} : PILAR (a) stabilitas + warm-up ===")
    print(f"N total {n} frame | warm-up boundary = {warmup} | steady = {len(tail)} frame\n")
    print("[STEADY-STATE / pilar a]  (siap kutip Bab IV)")
    print(f"  PRR            : {prr:.2f} %")
    print(f"  EVM            : {em:.2f} +/- {es:.2f} dB   (CV linear {cv_evm:.2f} %)")
    print(f"  |CFO|          : {cm:.0f} +/- {cs:.0f} Hz")
    print(f"  amp            : {am:.4f} +/- {asd:.4f}   (CV {cv_amp:.2f} %)")
    print(f"  OVF steady     : {ovf_rate:.2f} %/frame")

    # frames-to-settle: window 50-frame pertama yang masuk em +/- 2es
    lo, hi = em - 2*es, em + 2*es
    settle = None
    w = 50
    series = [_f(r.get("comm_evm_db")) for r in rows]
    for i in range(0, n-w):
        seg = [x for x in series[i:i+w] if x is not None]
        if seg and lo <= (sum(seg)/len(seg)) <= hi:
            settle = i; break
    print(f"  warm-up length : ~{settle if settle is not None else 'n/a'} frame "
          f"(EVM masuk steady +/-2SD)\n")

    print("[WARM-UP PROFILE / pilar b kondisi awal]  (untuk kurva Gambar)")
    print(f"  {'bin':>3} {'frame':>11} {'EVM dB':>8} {'amp':>8} {'ovf_cum':>9}")
    for b in range(nbin):
        s, e = b*binsz, (b+1)*binsz
        seg = rows[s:e]
        ev = [_f(r.get('comm_evm_db')) for r in seg]
        ev = [x for x in ev if x is not None]
        ap = [_f(r.get('amp')) for r in seg]
        ap = [x for x in ap if x is not None]
        ov = _f(seg[-1].get('ovf')) if seg else None
        evb = sum(ev)/len(ev) if ev else float('nan')
        apb = sum(ap)/len(ap) if ap else float('nan')
        print(f"  {b:>3} {f'{s}-{e}':>11} {evb:>8.2f} {apb:>8.4f} "
              f"{(int(ov) if ov is not None else 0):>9}")

# ---------- pilar (b) bandwidth ceiling : ringkasan sweep ----------
def analyze_sweep(path):
    rows = list(csv.DictReader(open(path)))
    print(f"\n=== {path} : PILAR (b) bandwidth ceiling ===")
    print("Diskriminatif = EVM + OVF cliff (PRR datar ~100%, bukan pembeda; lesson 8.12)\n")
    hdr = f"  {'fs MHz':>7} {'EVM dB':>8} {'OVF%/fr':>8} {'valid%':>7} {'BER':>9} {'pass':>5}  reason"
    print(hdr)
    last_pass = None
    cliff = None
    for r in sorted(rows, key=lambda x: _f(x.get("fs_mhz")) or 0):
        fs   = _f(r.get("fs_mhz"))
        evm  = _f(r.get("mean_evm_db"))
        ovf  = _f(r.get("ovf_rate_steady"))
        vr   = _f(r.get("valid_rate"))
        ber  = _f(r.get("mean_ber"))
        pas  = str(r.get("pass")).strip()
        rsn  = r.get("reason","")
        passed = pas in ("True","true","1")
        print(f"  {fs:>7.0f} {(evm if evm is not None else float('nan')):>8.2f} "
              f"{(ovf*100 if ovf is not None else float('nan')):>8.1f} "
              f"{(vr*100 if vr is not None else float('nan')):>7.1f} "
              f"{(ber if ber is not None else float('nan')):>9.4f} "
              f"{str(passed):>5}  {rsn}")
        if passed: last_pass = fs
        elif cliff is None and last_pass is not None: cliff = fs
    print()
    if last_pass is not None:
        print(f"  => Ceiling (fs tertinggi LULUS) : {last_pass:.0f} MHz")
    if cliff is not None:
        print(f"  => Cliff (fs pertama GAGAL)      : {cliff:.0f} MHz")
    print("  => Klaim sah: link stabil sampai ceiling; di atasnya OVF/EVM cliff (USB3.0 + filter AD9361).")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--warmup", type=int, default=500,
                    help="batas frame warm-up utk baseline (default 500)")
    a = ap.parse_args()
    for path in a.files:
        try:
            cols = next(csv.reader(open(path)))
        except Exception as e:
            print(f"[{path}] gagal dibuka: {e}"); continue
        if "fs_mhz" in cols:
            analyze_sweep(path)
        elif "frame_idx" in cols:
            analyze_baseline(path, a.warmup)
        else:
            print(f"[{path}] tipe tak dikenali (tak ada fs_mhz/frame_idx).")

if __name__ == "__main__":
    main()
