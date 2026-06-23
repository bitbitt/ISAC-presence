# CONTEXT TRANSFER — ISAC Bistatic OFDM (Internal Working Doc)

> Dokumen pengalih-konteks untuk lanjut di chat/sesi baru. Bukan untuk publik.
> Pasangan: `README.md` (publik/GitHub) + `ofdm_isac_bistatic_isac_presence-f.py` (kode).

**File kode:** `ofdm_isac_bistatic_isac_presence-f.py` (Python, UHD/SDR — BUKAN MATLAB)
**Hardware:** USRP B210 (TX) + LibreSDR (RX), bistatic, 2× antena omni. fs=40 MS/s, fc=5.9 GHz.
**Status:** Tuning JCAS final + static tervalidasi 0 FA (build presence-f). Presence **frame-native** (bug latch diperbaiki). **Walk-presence SUDAH tervalidasi hardware** (sesi data ini): 16 run walk @20k frame — latch fix terbukti hilang (transisi ON→OFF 4–39×/run, OCCUPIED expire normal), batas deteksi terukur (~≤2 m), trade-off comm terkuantifikasi (PRR worst-window anjlok ke 38–63%). Dataset final lengkap.

---

## 1. APA YANG SUDAH DILAKUKAN (ringkas)

Satu waveform OFDM → comm (QPSK, teks "STEI", PRR ~99–100%) + sensing (forward-scatter JCAS presence) dari frame yang SAMA. Sistem = **ISAC Level-1 (coexistence), communication-centric, single-stream/SISO bistatic**.

Perjalanan tuning (kronologis):
1. **FA static goyang (8 vs 29)** → root cause: Doppler tercemar CFO. Fix: `doppler_weight 1.0→0.1`, `dopp_sigma floor 2→50`. Static → 0 stabil.
2. **Walk putus-putus (self-masking)** → `ma_len 30→90` (baseline lambat lupa).
3. **cfar_len 360 bikin walk MISS** (sigma penyebut membengkak) → `cfar_len 360→120`. Static tetap 0.
4. **Event vs Presence** → pilih PRESENCE (state machine) untuk "deteksi orang lewat".
5. **BUG LATCH presence + migrasi frame-native** (sesi ini) → lihat bagian 5. Inti: hold presence dulu dikonversi dari detik pakai `fs/FRAME_LEN` (laju teoretis ~17.241/s, BUKAN FPS real ~13-15) → counter jadi ~206.897 frame ≫ run 5.000 frame → latch. Fix: hold langsung dalam frame (`presence_hold_frames=200`).

Model score: `score ≈ |amp_hp| / amp_sigma`
- `ma_len` → PEMBILANG (baseline amp_hp). Naik = anti self-masking.
- `cfar_len` → PENYEBUT (amp_sigma=MAD) + threshold. Naik = score tertekan saat walk.
- Arah BERLAWANAN — itu inti tuning.

Struktur waveform (rinci, hasil bedah sesi ini):
- Nfft=64, FRAME_LEN=2320 sample. Aktif `|k| 1..25`.
- **8 SC tengah (`k=±1..±4`) = QPSK** → payload comm.
- **38 SC = BPSK known (seed 123)** → referensi sensing forward-scatter.
- **4 pilot (`k=±7,±21`) = 1+0j** → referensi fasa (CPE).
- DC + `|k|≥26` = null/guard.
- Satu IFFT gabungkan semua → satu frame. RX: FFT memisahkan per-bin (ortogonal). Demod beda cuma di aturan keputusan per indeks SC (qpsk_demap vs `real()<0`). H_est, ekualisasi, koreksi pilot identik untuk dua grup.

---

## 2. PARAMETER FINAL (3 sumber harus konsisten: __init__/run_isac/argparse)

| Param | Nilai | Alasan |
|---|---|---|
| doppler_weight | 0.1 | Doppler tercemar CFO; amp jadi fitur utama |
| dopp_sigma floor | 50 Hz | CFO jitter tak jadi sinyal |
| ma_len | 90 | anti self-masking |
| cfar_len | 120 | responsif walk + static tetap 0 |
| threshold_k | 4.5 | CFAR multiplier |
| min_score | 2.5 | static p99 ~0.4, walk >5 |
| **presence_hold_frames** | **200** | **FRAME-NATIVE** — hold langsung dalam frame, TANPA `× fs_frame`. 200 ≪ 5000 → bisa expire, no latch |
| calib_frames | 400 | kalibrasi clutter (ruangan DIAM) |

CLI: `--sense-ma-len --sense-cfar-len --sense-threshold-k --sense-min-score --sense-presence-frames`. Default = nilai final.
**PERHATIAN:** flag presence sekarang `--sense-presence-frames` (int, frame), BUKAN lagi `--sense-presence-sec` (detik). Param lama `presence_timeout_sec` sudah dihapus total di 6 titik.

---

## 3. PROOF / VALIDASI

### 3.1 STATIC (3 run, build presence-f, 5k frame)
| Kondisi | Hasil |
|---|---|
| STATIC ×3 | **0/0/0 FA**, steady-state score_max **0.97 / 1.23 / 1.50** (≪2.5), PRR 99.94 / 99.96 / 99.98% |
| Spike warmup | frame 2–5 score 6–11 (TINGGI tapi DI-GATE, object_detected=0). Steady-state (>500): p99 ~0.38, mean ~0.15 |

### 3.2 WALK — TERVALIDASI HARDWARE (16 run, 20k frame/run)
Sweep jarak (1/2/3 m) × orientasi (horizontal = subjek motong tegak-lurus LoS; sampingrx = lintas di sisi RX) + skenario lintasanC.

| Run | Det frame /20k | ON→OFF | n_segmen | score_max | PRR | Worst-window PRR (100 frm) |
|---|---|---|---|---|---|---|
| 1m horiz ×2 | 12252 / 13851 | 37 / 31 | 38 / 32 | 10.2 / 11.3 | 99.10 / 99.15% | 87% |
| 1m sampingrx ×2 | 13060 / 12874 | 35 / 39 | 36 / 40 | 9.7 / 8.9 | 99.55 / 99.51% | — |
| 2m horiz ×2 | 5314 / 4372 | 22 / 19 | 22 / 19 | 4.8 / 5.0 | 99.84 / 99.85% | — |
| 2m sampingrx ×2 | 807 / 1654 | 4 / 7 | 4 / 7 | 3.2 / 4.0 | 99.58 / 99.58% | — |
| **3m ×4** | **0 / 0 / 0 / 0** | 0 | 0 | **1.70–2.04** | 99.74–99.80% | — |
| lintasanC 2orang depan-belakang | 5993 | 22 | 22 | 8.8 | **96.84%** | **38%** |
| lintasanC bawaHP5G ×2 | 6361 / 7264 | 19 / 21 | 20 / 22 | 21.1 / 17.2 | 98.49 / 98.83% | 63% |
| lintasanC tanpaHP | 5750 | 16 | 17 | 16.6 | 98.10% | 43% (EVM peak +5.6 dB) |

**Kesimpulan kunci:**
1. **LATCH HILANG (terbukti hardware).** Tiap run yang mendeteksi punya transisi ON→OFF (4–39×) + n_segmen OCCUPIED terpisah ≈ jumlah ON→OFF. Median panjang segmen ~200–347 frame ≈ hold window (200). Counter expire normal, TIDAK nyangkut. Ini bukti end-to-end yang sebelumnya cuma unit-test.
2. **Batas deteksi ≈ ≤2 m.** Di 3 m, score puncak **1.70–2.04 < floor 2.5** → **0 deteksi di 4 run**. Forward-scatter jatuh di bawah floor pada jarak ini (setup + threshold ini). Orientasi penting: di 2 m, horizontal (4–5k det) ≫ sampingrx (0.8–1.6k det) — crossing tegak-lurus LoS memberi shadowing lebih kuat.
3. **Trade-off ISAC terkuantifikasi TAJAM.** Worst 100-frame window: PRR anjlok ke **38–63%** (multi-body / lintasan lambat lewat PUSAT LoS) vs 99% static. EVM mengayun dari ~−11 dB (bersih) → mean-window ~−6 dB, **puncak +5 dB** persis saat block. Comm garbled = bukti sensing valid (event fisik sama memicu deteksi DAN merusak comm).

**Catatan anti-over-claim (PENTING):** skenario bawaHP5G vs tanpaHP **dua-duanya terdeteksi kuat** — mekanisme deteksi adalah **shadowing TUBUH (forward-scatter)**, BUKAN emisi 5G HP. Selisih score_max (21 vs 16) ada dalam rentang variabel-manusia run-to-run, **bukan** klaim "deteksi HP". Jangan klaim sistem mendeteksi perangkat 5G.

---

## 4. POSITIONING (PENTING — jangan over-claim)

**Yang BENAR diklaim:** demonstrator ISAC/JCAS communication-centric berbasis OFDM di SDR riil; coexistence sensing+comm; trade-off comm-vs-sensing terukur (PRR worst-window 38–63%); presence detection forward-scatter pada link bistatik **tervalidasi hardware** (16 run walk); state machine frame-native **terbukti clear normal di hardware** (ON→OFF, no latch); **batas jangkauan terukur ~≤2 m**.

**Yang SALAH / jangan diklaim:**
- BUKAN ISAC 6G penuh (tak ada MIMO, beamforming, angle/AoA estimation).
- BUKAN localization/triangulasi (single bistatic link = presence + range kasar, bukan posisi x,y). Kata "triangulasi" = KELIRU untuk 1 link.
- Range/echo (Phase 1C) = konteks visual saja, BUKAN klaim deteksi.
- Kodenya PYTHON/UHD, **bukan MATLAB**. (Kalau ada yang sebut "kode matlab" — itu keliru.)
- **BUKAN deteksi perangkat 5G.** bawaHP5G & tanpaHP dua-duanya terdeteksi — mekanisme = shadowing tubuh (forward-scatter), bukan emisi HP. Jangan klaim "mendeteksi HP 5G".
- **Jangan klaim deteksi >2 m** untuk setup ini — di 3 m score < floor (2.5), 0 deteksi di 4 run. Batas jangkauan = sifat setup+threshold, bukan bug.
- Jangan sebut hold "12 detik" lagi — sekarang frame-native (200 frame). Angka detik baru valid setelah ada timestamp & FPS terukur.

---

## 5. BUG YANG SUDAH DIPERBAIKI
- **[BARU sesi ini] BUG LATCH presence (fatal di run walk).**
  - Gejala: presence bakal nyangkut OCCUPIED selamanya begitu deteksi pertama saat walk. Tak ketahuan di static (static tak pernah trigger → counter tak pernah di-set).
  - Root cause: `_presence_timeout = round(presence_timeout_sec × fs_frame)`, `fs_frame = fs/FRAME_LEN = 40e6/2320 = 17.241/detik`. Jadi `round(12 × 17.241) = 206.897 frame`. Run cuma 5.000 frame → 206.897 ≫ 5.000 → tak pernah expire. Terbukti dari aritmetika frame saja, tak butuh FPS.
  - Bukti angka (eksekusi, bukan kira-kira): `python3 -c "print(round(12.0*(40e6/2320)))"` → `206897`.
  - Fix: FRAME-NATIVE. `_presence_timeout = int(max(1, presence_hold_frames))`, default 200. Hapus `× fs_frame` di semua titik. Diverifikasi unit test: presence clear normal, no latch. **[UPDATE sesi data ini] TERKONFIRMASI HARDWARE:** 16 run walk @20k frame, tiap run yang mendeteksi punya transisi ON→OFF (4–39×) + segmen OCCUPIED terpisah (median ~200–347 frame ≈ hold). Counter expire normal end-to-end. Latch hilang terbukti, bukan lagi sekadar unit-test.
  - 6 titik diubah: `__init__` (param+konversi, baris ~1035 & 1050), `run_isac` (signature ~1377 & call ~1499), argparse (~2150), penerusan args (~2208). Plus 1 docstring (baris 19).
- Legacy line leak (frame drop tampil format Phase 0) → cetak `[drop]` seragam.
- Banner "Decoded X/Y" menyesatkan → "Packets: N (target M frame)".
- Warmup spike live print → tampil "warm".
- Konsistensi default 3-sumber (dulu argparse pakai nilai lama → tuning tak aktif saat run telanjang).
- Bug "off-by-one [CAL]" → ternyata BUKAN bug (300/400 frame kalibrasi benar).

---

## 6. GOTCHA TEKNIS
- **[KOREKSI penting] `fs/FRAME_LEN` ≠ FPS real.** `fs/FRAME_LEN = 40e6/2320 = 17.241/detik` itu laju **teoretis** (kalau tiap slot 58 µs jadi 1 frame back-to-back), **BUKAN** laju frame nyata yang masuk `update()`. FPS real ~13-15/detik (dibatasi USB + demod Python). Catatan lama yang nulis "~17 teoretis FPS" itu salah-label — angkanya 17 RIBU, bukan 17. Jangan pakai `fs/FRAME_LEN` untuk konversi waktu→frame.
- **Notasi titik/koma.** "17.241" = tujuh belas RIBU (pemisah ribuan), bukan 17,2 desimal. Salah baca ini bikin error 1000×. Verifikasi angka dengan EKSEKUSI, bukan baca.
- **Hold > panjang run = latch diam-diam.** Counter hold apa pun WAJIB dicek terhadap total frame run. Kalau timeout ≫ total frame, state tak pernah clear, dataset rusak tanpa error.
- **Static tak menguji jalur presence.** Static tak pernah trigger → hold/latch tak terpanggil. Logika hold HARUS diuji dengan walk.
- **FPS real belum terukur** (no timestamp di CSV). "Berapa detik" run = belum pasti. Frame-native bikin ini tak relevan untuk hold.
- **OVF ~4%/frame:** tak hilangkan baris CSV (frame_idx kontinu), tapi bisa rusak frame saat objek lewat. Pantau; >8-10% → kurangi fs / perbesar recv chunk.
- **DROP ≠ CRC-fail:** DROP (hilang USB) tak masuk PRR; CRC-fail masuk PRR. Laporkan keduanya.
- **cfar_len > ma_len WAJIB** (kode paksa `max(ma_len+5, cfar_len)`).
- **Kalibrasi 400 frame awal WAJIB DIAM.** Walk: tunggu pesan `[CALIB] FASE DETEKSI mulai` baru gerak.

---

## 7. STATUS DOKUMEN / TODO
- [x] **Docstring cfar_len BASI** → sudah cfar_len=120 di build sekarang.
- [x] **Migrasi presence ke frame-native** → selesai, 6 titik, unit-tested.
- [x] **README & CONTEXT_TRANSFER** disinkronkan ke build presence-f (frame-native).
- [x] **Walk-presence diuji penuh di HARDWARE** → SELESAI (sesi data ini): 16 run @20k, latch hilang terkonfirmasi (ON→OFF 4–39×/run), durasi OCCUPIED & lag clear terlihat (segmen median ~200–347 frame), batas jangkauan ~≤2 m terukur.
- [x] **Dataset final** → ada: 3× static + sweep 1/2/3 m × horiz/sampingrx + 4 skenario lintasanC.
- [ ] Timestamp di CSV (ukur FPS aktual → bisa laporkan hold & durasi OCCUPIED dalam detik dengan yakin). **Masih relevan** — durasi "frame" sudah valid, "detik" belum.
- [ ] (Opsional) Tuning ulang threshold/hold untuk perpanjang jangkauan ke 3 m (turunkan floor / naikkan gain) — trade-off vs FA static harus dicek ulang.
- [ ] Opsional ISAC Level-2: adaptive modulation QPSK↔BPSK berbasis flag deteksi.

---

## 8. WORKPLAN (langkah berikutnya, urut)
1. [x] **Walk-presence di hardware** — SELESAI. Cek latch (output nyata, build ini):
   `python3 -c "import csv; r=[x['jcas_object_detected'] for x in csv.DictReader(open('walk.csv'))]; print('ON:',r.count('1'),'OFF:',r.count('0'),'| ON->OFF:',sum(1 for i in range(1,len(r)) if r[i-1]=='1' and r[i]=='0'))"`
   → semua run mendeteksi menghasilkan ON→OFF > 0 (mis. 1m horiz-1: ON 12252, OFF 7757, ON→OFF **37**). Latch hilang.
2. [x] **Dataset final** terkumpul (static ×3 + sweep jarak/orientasi + lintasanC).
3. **Tuning `presence_hold_frames`** kalau perlu: dari data, segmen OCCUPIED median ~200–347 frame ≈ hold 200 → wajar. Sering putus di 2 m sampingrx (segmen pendek) → bisa naikkan hold. Pakai `--sense-presence-frames`, tanpa edit kode.
4. **Tambah timestamp per-frame di CSV** → ukur FPS aktual → konversi hold & durasi OCCUPIED (frame→detik) untuk pelaporan.
5. (Opsional) Perpanjang jangkauan ke 3 m: turunkan `min_score` / naikkan gain RX → WAJIB re-cek FA static (score static max 0.97–1.50; floor di bawah ~2.0 mulai berisiko FA).
6. (Opsional) ISAC Level-2 adaptive modulation kalau mau naik level.

---

## 9. CHAT BARU — LAMPIRKAN APA
**Wajib:**
- `CONTEXT_TRANSFER.md` (file ini)
- `ofdm_isac_bistatic_isac_presence-f.py` (kode terbaru, frame-native)

**Sangat disarankan:**
- CSV static: `presence_static_f_1/2/3.csv`
- CSV walk-presence (SUDAH ADA, dataset final): sweep `presence_walk-{1,2,3}m_{horizontal,sampingrx}-{1,2}.csv` + skenario `presence_walk-lintasanC-*.csv` (2orang, bawaHP5G, orangtanpaHP). Cukup bawa 2–3 perwakilan (mis. 1m_horizontal, 2m_sampingrx, lintasanC tanpaHP) — tak perlu semua 16.

**JANGAN bawa (sudah terangkum / tak relevan, bikin berat):**
- File kode LAMA: `ofdm_isac_bistatic_isac_demo.py`, `demo-2.py`, `demo-3.py` (semua digantikan oleh `presence-f.py`).
- CSV LAMA: `presence_static.csv` / `-2` / `-3` (baseline lama, sudah di-summary), `test_fix_*`, `cek_walk`, `data-3`.

**Kalimat pembuka:** "Lanjutan ISAC. Konteks di CONTEXT_TRANSFER.md, kode di presence-f.py. Mau [tugas]."

**PERINGATAN:** pastikan .md & .py yang dilampir = versi sinkron. Kalau sudah edit kode setelah .md dibuat, update dulu bagian Validasi & TODO & Parameter Final.

---

## 10. CEK KONSISTENSI CEPAT (tiap habis tuning)
```bash
python3 -c "import ast; ast.parse(open('ofdm_isac_bistatic_isac_presence-f.py').read()); print('OK')"
grep -n "presence_hold_frames" ofdm_isac_bistatic_isac_presence-f.py   # 5 occurrence symbol (default 200): __init__ sig+body, run_isac sig+call, args-forward
grep -n "sense-presence-frames" ofdm_isac_bistatic_isac_presence-f.py  # +1 flag argparse = 6 titik migrasi total
grep -n "presence_timeout_sec\|sense-presence-sec" ofdm_isac_bistatic_isac_presence-f.py  # HARUS KOSONG
python3 ofdm_isac_bistatic_isac_presence-f.py --help | grep presence    # flag = --sense-presence-frames
python3 -c "print(round(12.0*(40e6/2320)))"   # =206897, bukti kenapa konversi detik dulu salah
```
Aturan ganti setup fisik: static score_max < ~1.5 DAN walk > ~5 → threshold 2.5 aman tanpa re-tune.
