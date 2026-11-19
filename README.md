# Alih — Terjemah Indonesia ⇄ Inggris

Web penerjemah lokal dua arah menggunakan Helsinki-NLP `opus-mt-id-en` dan `opus-mt-en-id`, keduanya dikonversi ke CTranslate2 INT8 untuk mengendalikan penggunaan memori dan CPU. Model dimuat saat permintaan terjemahan pertama lalu dilepas setelah 120 detik tanpa aktivitas; saat idle, proses web tidak menjalankan inferensi. Teks diproses pada server ini, bukan layanan inference pihak ketiga.

## Jalankan

```bash
./start.sh
```

Buka `http://<IP-server>:8789`. Status model: `http://<IP-server>:8789/api/health`.

## Bangun ulang model

Model tidak ikut repo (folder `models/` di-.gitignore). Untuk membuat ulang dari nol:

```bash
./scripts/build_model.sh
```

Skrip mengunduh kedua repo Helsinki-NLP dari Hugging Face, mengonversi ke CTranslate2 INT8, menyalin tokenizer, lalu menyimpannya di `models/opus-mt-id-en-ct2/` dan `models/opus-mt-en-id-ct2/` (masing-masing ±75 MB). Butuh koneksi internet dan ruang disk ±800 MB selama proses.

## Autostart

Unit systemd user tersedia di `deploy/id-en-translator.service`:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/id-en-translator.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now id-en-translator
loginctl enable-linger "$USER"
```

## Arah terjemahan

UI punya tiga mode: `Auto`, `ID→EN`, `EN→ID`, plus tombol tukar arah.

API menerima field `direction`:

```bash
curl -X POST http://127.0.0.1:8789/api/translate \
  -H 'Content-Type: application/json' \
  -d '{"text":"Selamat pagi semua","direction":"id-en"}'
```

Nilai yang diterima: `id-en`, `en-id`, atau `auto` (default). Mode `auto` mendeteksi bahasa sumber dari kata fungsi yang khas; bila ambigu, jatuh ke `id-en`. Respons menyertakan `direction` dan `model` yang benar-benar dipakai.

## Konfigurasi

| Env | Default | Fungsi |
| --- | --- | --- |
| `MODEL_DIR_ID_EN` | `models/opus-mt-id-en-ct2` | Lokasi model ID→EN |
| `MODEL_DIR_EN_ID` | `models/opus-mt-en-id-ct2` | Lokasi model EN→ID |
| `CPU_THREADS` | `2` | Thread CPU per inferensi |
| `IDLE_UNLOAD_SECONDS` | `120` | Jeda sebelum model dilepas (min 30) |
| `HOST` / `PORT` | `0.0.0.0` / `8789` | Bind address |

Dependensi Python tercatat di `requirements.txt`; model terkonversi disimpan di `models/`. Model dan tokenizer harus sudah tersedia lokal agar aplikasi dapat dimulai dan melayani terjemahan.

Batas input per permintaan: 5.000 karakter. Backend dijalankan satu worker; inferensi menggunakan maksimal dua thread CPU secara default, diatur lewat `CPU_THREADS`. Ketika request berlangsung, model memakai thread CPU yang dikonfigurasi; saat tidak ada request CPU untuk inferensi nol. Mengosongkan model dapat mengembalikan RAM ke sistem, namun halaman berstatus tidur hingga permintaan berikutnya memuat model lagi. Saat kedua arah aktif bersamaan, RSS proses sekitar 640 MB; turun kembali setelah idle unload.

Model: [Helsinki-NLP/opus-mt-id-en](https://huggingface.co/Helsinki-NLP/opus-mt-id-en) · [Helsinki-NLP/opus-mt-en-id](https://huggingface.co/Helsinki-NLP/opus-mt-en-id) · lisensi Apache-2.0.
