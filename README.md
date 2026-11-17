# Alih — Terjemah Indonesia ke Inggris

EXSALA HERMES MOD · powered by Gienetic

Web penerjemah lokal menggunakan Helsinki-NLP `opus-mt-id-en`, dikonversi ke CTranslate2 INT8 untuk mengendalikan penggunaan memori dan CPU. Model dimuat saat permintaan terjemahan pertama lalu dilepas setelah 120 detik tanpa aktivitas; saat idle, proses web tidak menjalankan inferensi. Teks diproses pada server ini, bukan layanan inference pihak ketiga.

## Jalankan

```bash
./start.sh
```

Buka `http://<IP-server>:8789`. Status model: `http://<IP-server>:8789/api/health`.

Dependensi Python tercatat di `requirements.txt`; model terkonversi disimpan di `models/opus-mt-id-en-ct2/`. Model dan tokenizer harus sudah tersedia lokal agar aplikasi dapat dimulai dan melayani terjemahan.

Batas input per permintaan: 5.000 karakter. Backend dijalankan satu worker; inferensi menggunakan maksimal dua thread CPU secara default, diatur lewat `CPU_THREADS`. Jeda idle bawaan 120 detik; dapat diubah lewat `IDLE_UNLOAD_SECONDS` (minimum 30 detik). Ketika request berlangsung, model memakai thread CPU yang dikonfigurasi; saat tidak ada request CPU untuk inferensi nol. Mengosongkan model dapat mengembalikan RAM ke sistem, namun halaman berstatus tidur hingga permintaan berikutnya memuat model lagi.

Model: [Helsinki-NLP/opus-mt-id-en](https://huggingface.co/Helsinki-NLP/opus-mt-id-en) · lisensi Apache-2.0.
