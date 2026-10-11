# Roadmap Status

Update: 2026-07-31

## Executive Summary

KT Auto Trading Bot sudah berjalan di VPS managed dan layak masuk fase early access terbatas, bukan public mass release.

Status yang disarankan:

- Managed VPS live: yes.
- Early access terbatas: yes, dengan filter user.
- Public mass sale: belum.
- Claim profit: tidak boleh.
- Fokus beta: stabilitas, safety, report accuracy, user experience.

## Fase 1: Hardening Bot

Status: mostly complete.

Selesai:

- Realized PnL diprioritaskan dalam report.
- Audit posisi tanpa SL.
- Audit orphan order.
- Startup reconciliation.
- Config eksternal.
- Backup journal otomatis.
- Simulate mode dipertahankan.

Masih perlu dipantau:

- Konsistensi sync pada akun dengan posisi manual campuran.
- Perilaku order conditional Binance jika ada perubahan endpoint/rule.
- Recovery dari koneksi internet putus panjang.

## Fase 2: Telegram Product Layer

Status: strong MVP.

Selesai:

- Command dasar.
- Pause/resume.
- Status posisi live.
- Report manual.
- Weekly/monthly performance report.
- Risk view.
- Health check.

Belum:

- Multi-user role.
- Admin-only multi user.
- License key.

## Fase 3: Private Beta

Status: ready to run as managed early access.

Langkah berikut:

- Pilih 5-10 tester.
- Pakai onboarding doc.
- Wajib simulate 24 jam.
- Wajib `/health` OK sebelum real mode.
- Jalankan 30 hari.
- Kumpulkan bug dengan template.
- Buat weekly transparent report.

## Fase 3B: VPS Managed Deployment

Status: live.

Selesai:

- VPS Biznet Gio NEO Lite aktif.
- SSH keypair baru aktif.
- Password SSH dinonaktifkan lagi.
- Bot berjalan sebagai systemd service.
- Auto-start saat VPS reboot.
- Journal dan shadow state sudah dipindahkan ke VPS.
- Log dan heartbeat aktif di VPS.

Catatan operasional:

- Laptop tidak perlu menyala 24 jam.
- Jangan jalankan bot laptop bersamaan dengan VPS.
- Update script berikutnya harus di-deploy ulang ke VPS.

## Fase 4: Monetisasi Awal

Status: prepare launch assets.

Syarat sebelum monetisasi:

- Minimal 30 hari beta.
- Bug critical nol.
- Dokumentasi setup sudah diuji oleh tester non-teknis.
- Track record transparan tersedia.
- Support workflow jelas.

Dokumen pendukung:

- `docs/LAUNCH_AND_PROMOTION_PLAN.md`
- `docs/CONTENT_BANK.md`

## Fase 5: Strategy A/B/C Research

Status: closed and frozen; no validated entry edge; no production integration.

Selesai:

- ABC v1 multi-pair development gate dijalankan dan gagal.
- ABC v2 dipisahkan sebagai mesin BTC-only research.
- Hierarki level 1D, struktur 4H, dan trigger 15m diterapkan.
- Level/range lineage dan transisi A/B/C eksklusif diterapkan.
- C tidak lagi memiliki scanner independen.
- Workbench review 150 chart BTC dibuat.
- Calendar dan derivatives tidak menjadi hard filter.
- SL/TP produksi tidak diubah.
- Empat hipotesis v2.1 diuji tanpa kandidat yang lulus penuh.
- Confirmed-A v2.2 ditolak pada periode 2022-2024: -5.511R.
- Balanced-range A v2.3 menghasilkan +2.158R pada holdout 2020-2022.
- V2.3 tetap ditolak karena hanya 4 trade dan 2 fold aktif.
- Gate lama dibuktikan mustahil karena hanya memiliki 3 event B.
- Workbench lama diganti dengan review buta dataset `0e90e449d059`.
- Coverage baru: A=52, B=19, C=43, control=36.
- Expected path, arah, transition, konteks, dan outcome disembunyikan.
- Label dikunci setelah aftermath dibuka.
- Desktop, mobile, import/export, dan aftermath-lock sudah diverifikasi.
- Seluruh 141 unit test lulus.
- Seluruh 150 chart blind sudah direview; 149 label diterima dan 1 dilewati.
- Exact agreement manusia/mesin hanya 38,60%.
- Human reviewer menemukan setup pada 31 dari 35 control chart.
- Outcome gabungan tetap negatif: 96 trade, -3,870R, PF 0,922.
- Semua jalur tetap `RESEARCH_ONLY`; tidak ada promosi ke forward shadow.
- Structured adjudication workbench 36 chart dibuat dari konflik paling
  informatif tanpa menggunakan P&L.
- Adjudication mencatat level, arah, acceptance, retest, sweep, reclaim, dan MSS
  sebagai field wajib.
- Browser adjudication tidak memiliki aftermath dan tidak menerima answer key.
- QA desktop, mobile, canvas, validation, import/export lulus.
- Seluruh 145 unit test lulus.
- Adjudication final selesai: 35 label diterima dan 1 dilewati.
- Minimum checklist lama overlap pada 21 dari 35 label.
- Human path hanya 22,86% konsisten dengan review pertama.
- V2.4 membekukan prioritas state C/B/A tanpa tuning angka.
- Replay V2.4 menghasilkan 101 trade, -6,539R, dan PF 0,876.
- Stress V2.4 menghasilkan -12,013R.
- A hanya +0,534R sebelum stress dan -1,469R setelah stress.
- Audit 122 event menunjukkan fixed-horizon edge 4h, 12h, dan 24h tidak
  berbeda signifikan dari nol.
- V2.4 ditolak untuk live dan forward shadow.
- Seluruh 156 unit test lulus setelah implementasi riset V2.4.

Keputusan:

- V2.4 dibekukan sebagai hasil gagal.
- A/B/C tidak dituning lagi pada replay 2019-2026.
- Tidak ada jalur A, B, atau C yang dipromosikan ke forward shadow.
- Riset baru dipisahkan dari S/R agar hasil lama tidak didaur ulang menjadi
  filter baru.

Dokumen pendukung:

- `docs/STRATEGY_ABC_V2_BTC_STRUCTURE_SPEC_2026-07-30.md`
- `docs/STRATEGY_ABC_V2_IMPLEMENTATION_2026-07-30.md`
- `docs/STRATEGY_ABC_V23_BALANCED_RANGE_SPEC_2026-07-30.md`
- `docs/STRATEGY_ABC_V23_HOLDOUT_RESULT_2026-07-30.md`
- `docs/STRATEGY_ABC_BLIND_LABEL_PROTOCOL_2026-07-30.md`
- `docs/STRATEGY_ABC_HUMAN_LABEL_GATE_RESULT_2026-07-30.md`
- `docs/STRATEGY_ABC_ADJUDICATION_PROTOCOL_2026-07-30.md`
- `docs/STRATEGY_ABC_HUMAN_STRUCTURE_SPEC_V24_2026-07-31.md`
- `docs/STRATEGY_ABC_V24_RESEARCH_RESULT_2026-07-31.md`

## Fase 6: Strategy D1 Time-Series Momentum

Status: LONG-only forward shadow active on VPS; SHORT rejected; no live
orders.

Selesai:

- Spesifikasi D1 dibekukan sebelum hasil dibuka.
- D1 dipisahkan sepenuhnya dari S/R, EMA, OI, calendar, dan mesin A/B/C.
- BTCUSDT 4H diuji dari 2019-09-01 sampai 2026-07-22.
- Development dan holdout diuji terpisah.
- Wilder ATR dan replay per sisi diaudit dan diperbaiki sebelum hasil final.
- LONG-only menghasilkan 238 trade, +57.100R, PF 1.771, DD 10.643R.
- Stress LONG-only menghasilkan +46.904R, PF 1.594, DD 11.625R.
- SHORT menghasilkan -8.178R dan ditolak.
- Runner forward shadow LONG-only dibuat tanpa dependensi eksternal.
- State atomik, first-run suppression, dan deduplikasi diuji.
- QA 15.051 candle dua kali menghasilkan nol duplicate event.
- Timer VPS terisolasi aktif setiap 15 menit.
- Unit shadow tidak dapat membaca folder, config, atau credential bot live.
- Poll publik pertama dan kedua sukses; posisi awal netral dan event ganda nol.
- Worker live tetap pada PID yang sama dengan restart count nol.
- Bot produksi, Telegram, SL, TP, dan risk tidak diubah.

Batasan:

- Stress median trade masih negatif.
- Interval estimasi mean masih melewati nol.
- Hanya 3 dari 7 tahun non-empty yang positif.
- Lima trade terbaik membawa lebih dari seluruh stress return.
- Hasil ini adalah kandidat historis, bukan edge live yang sudah terbukti.

Gate berikut:

- Kumpulkan LONG-only tanpa order minimal 270 hari dan 30 trade baru.
- Catat fee, slippage, dan funding aktual.
- Wajib actual-net R positif, PF minimal 1.15, dan DD maksimal 12R.
- Wajib tetap positif setelah trade terbaik dibuang.
- Parameter tidak boleh diubah selama forward gate.

Dokumen pendukung:

- `docs/STRATEGY_D1_TSMOM_FROZEN_SPEC_2026-07-31.md`
- `docs/STRATEGY_D1_TSMOM_RESULT_2026-07-31.md`
