# schematic-compare

Tool untuk membandingkan dua PDF skema (versi lama dan versi baru) dan membuat **Change Point List** dalam bentuk Excel, dengan pola yang sama seperti `CHANGE.POINT.LIST.CIRCUIT.DRAWING.xlsx`.

## Isi file Excel

| Sheet | Isi |
|---|---|
| Overview | Gambar block diagram kedua versi, info dokumen, pemetaan sheet, ringkasan jumlah (formula), catatan, Check Items dari config |
| Change Point List | Part yang berubah: Ref, nilai dan footprint sebelum/sesudah, Mounting After (formula), Remarks (Added / Removed / Changed / Moved) |
| Circuit Diagram Change | Potongan gambar per blok rangkaian, BEFORE dan AFTER, dengan ringkasan perubahan otomatis |
| Pin Change `<Ref>` | Hanya kalau diminta (`--pins J1`): pin konektor yang nama net-nya berubah |
| Extraction Review | Teks yang tidak bisa dipasangkan dengan yakin, ditambah daftar blok yang terdeteksi. Dipakai untuk mengisi config. |

## Kebutuhan

- Windows dengan Python 3.12 (`py -3.12`).
- PDF skema yang teksnya bisa diseleksi, misalnya hasil export OrCAD atau Print to PDF. Halaman berupa gambar (scan, screenshot) tetap ikut dipotong gambarnya, tapi part-nya tidak bisa dibaca.

Pemakaian pertama membuat `.venv` di folder ini dan memasang library dari `requirements.txt` secara otomatis.

## Pemakaian

### Drag and drop

Seret dua PDF (urutan bebas) ke `drop_here.bat`. Boleh sekalian menyeret satu file config `.json`. PDF yang lebih tua otomatis dianggap versi lama (berdasarkan tanggal di title block).

Output disimpan di folder PDF yang lebih baru dengan nama `CHANGE.POINT.LIST_<lama>_vs_<baru>.xlsx`. Kalau nama itu sudah ada, dibuat `_1`, `_2`, dan seterusnya. File lama tidak pernah ditimpa.

### Command line

```
sch_compare.bat LAMA.pdf BARU.pdf [opsi]
```

| Opsi | Fungsi |
|---|---|
| `-o OUT.xlsx` | Lokasi output |
| `-c config.json` | Pakai config (lihat di bawah) |
| `--before-name Joystick` / `--after-name Joystick2` | Label versi di Excel (default: nama file) |
| `--pins J1 J2` | Bandingkan net per pin untuk konektor tersebut |
| `--auto-order` | Tukar input kalau LAMA ternyata lebih baru |
| `--dump FOLDER` | Simpan hasil baca (part, blok, baris) sebagai JSON untuk debugging |

## Alur kerja yang disarankan

1. Jalankan tanpa config.
2. Buka sheet **Extraction Review**:
   - *part without value*: nilai part tidak ketemu (biasanya IC yang nilainya ditulis jauh dari simbol).
   - *value taken from far text*: nilai diambil dari teks yang agak jauh. Cek sekilas.
   - *value text not linked to a part*: ada teks nilai yang tidak terpasang ke part mana pun.
   - Daftar blok: nama otomatis tiap blok, dipakai untuk mengganti nama blok tanpa judul.
3. Salin `examples/joystick_vs_joystick2.json`, ubah isinya untuk pasangan skema yang baru.
4. Jalankan ulang dengan `-c config.json` (atau seret `.json` bersama kedua PDF).
5. Tambahkan catatan review di `block_remarks` dan `check_items` kalau hasilnya akan dibagikan.

## Config

Semua kunci opsional. Kunci yang salah ketik langsung ditolak dengan pesan error.

| Kunci | Isi | Contoh |
|---|---|---|
| `before_name`, `after_name` | Label versi | `"Joystick"` |
| `value_overrides` | Koreksi nilai/footprint per Ref, dipisah `before` / `after` | `{"after": {"U17": {"value": "PY32F040R1BT6-LQFP-64"}}}` |
| `block_names` | Ganti nama blok. Kunci = `sheet:nama otomatis` dari Extraction Review | `{"after": {"6:Untitled p6 (SW7)": "Trigger Keys"}}` |
| `block_pairs` | Paksa pasangan blok lama dan baru kalau namanya beda jauh | `[["Mappable Action Buttons", "Back Buttons"]]` |
| `block_remarks` | Catatan per blok (nama blok versi baru, atau versi lama untuk blok yang dihapus). Ditaruh di atas ringkasan otomatis. | `{"Charger": "SS88C9H diganti AW32001A"}` |
| `auto_remarks` | `false` untuk mematikan ringkasan otomatis di Circuit Diagram Change | `true` |
| `check_items` | Daftar temuan review untuk Overview, berisi pasangan `[sheet, teks]` | `[["05 BTB", "Catatan pin 1 tidak cocok"]]` |
| `pins` | Konektor yang dibandingkan per pin | `["J1"]` |
| `exclude_prefixes` | Prefix Ref yang tidak dimasukkan ke daftar | `["T", "TP"]` |
| `no_value_prefixes` | Prefix Ref yang memang tidak punya nilai (test point dan sejenisnya) | `["T", "TP", "NP", "AA"]` |

## Cara kerja singkat

| Langkah | Cara |
|---|---|
| Teks part | Warna yang paling sering dipakai teks berbentuk Ref (R12, U4, SW7) dianggap warna part. Semua teks berwarna itu adalah Ref atau nilai. Teks "NC" dengan warna yang jarang dipakai (markup designer) juga dihitung sebagai nilai. |
| Ref ke nilai | Nilai dicari di kanan Ref pada baris yang sama, tepat di bawah Ref, atau satu baris lebih rendah di kanan. IC dan konektor boleh lebih jauh, dan yang seperti ini ditandai di Extraction Review. Teks Ref dan nilai yang menempel (`RZA790R`) dipecah dulu. |
| Footprint | Teks hitam berpola `R0402`, `C0201`, `SOD-123...`, dan sejenisnya yang sejajar dengan nilai |
| Blok | Area dibatasi garis tebal (garis yang menggantung diperpanjang), lalu kotak atau garis putus-putus yang besar. Judul blok adalah teks besar di dekat pojok kiri atas area. Blok tanpa judul dinamai `Untitled pN (Ref utama)`. |
| Perbandingan | Per Ref. Blok lama dan baru dipasangkan berdasarkan nama, lalu kesamaan part, lalu kata yang sama di nama blok. |
| Pin konektor | Badan simbol dicari dari garis yang mulai tepat di bawah teks Ref. Net diikuti dari ujung pin sepanjang kabel sampai ketemu label net. |

## Keterbatasan

- Ini bukan pembanding netlist. Perubahan sambungan kabel hanya terlihat di gambar Circuit Diagram Change, kecuali pin konektor yang diminta lewat `--pins`.
- Pembacaan bergantung pada gaya gambar. Dirancang dan diuji pada export OrCAD (contoh Joystick). Skema dari EDA lain mungkin butuh koreksi lewat config lebih banyak.
- Ref yang dipakai ulang untuk fungsi lain tercatat sebagai Changed atau Moved.
- Analisis desain (Check Items) tetap diisi engineer. Tool hanya membuat ringkasan perubahan.

## Test

```
.venv\Scripts\python -m pytest
```

`tests/test_samples.py` memakai PDF contoh Joystick dan otomatis dilewati kalau file tidak ada. Path-nya bisa diatur lewat environment variable `SCH_COMPARE_BEFORE` dan `SCH_COMPARE_AFTER`.

## Struktur

| Path | Isi |
|---|---|
| `sch_compare/pdfdoc.py` | Baca PDF: teks, garis, bingkai halaman, title block |
| `sch_compare/parts.py` | Ref, nilai, footprint |
| `sch_compare/blocks.py` | Blok rangkaian dan area potongan gambar |
| `sch_compare/compare.py` | Pasangan blok, perbandingan per Ref, ringkasan per blok |
| `sch_compare/pins.py` | Net per pin konektor |
| `sch_compare/excel.py` | Penulis workbook |
| `sch_compare/cli.py` | Perintah utama dan mode drag and drop |
| `examples/` | Config contoh (Joystick vs Joystick2) |
| `tests/` | Unit test dan test dengan PDF contoh |
