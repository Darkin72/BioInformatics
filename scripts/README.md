# Scripts váº­n hÃ nh

ThÆ° má»¥c nÃ y chá»©a cÃ¡c script há»— trá»£ phÃ¡t triá»ƒn, kiá»ƒm thá»­ vÃ  váº­n hÃ nh local.

## Stress test gá»­i nhiá»u file sequence

Script [stress_submit_sequences.py](stress_submit_sequences.py) Ä‘á»c nhiá»u file `.fa`, `.fasta`, `.faa`, `.fna` hoáº·c `.txt`, Ä‘Äƒng nháº­p vÃ o Serving API, rá»“i gá»­i Ä‘á»“ng thá»i cÃ¡c sequence vÃ o endpoint `/api/inference-requests`.

Táº¡o nhanh 20 file FASTA máº«u vÃ  gá»­i vá»›i 8 worker:

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\tmp\stress_sequences `
  --create-samples 20 `
  --workers 8 `
  --username your_user `
  --password your_password
```

Cháº¡y trÃªn thÆ° má»¥c dá»¯ liá»‡u cÃ³ sáºµn:

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\data\stress_sequences `
  --workers 8 `
  --repeat 2 `
  --output stress-results.jsonl `
  --username your_user `
  --password your_password
```

Chá»‰ kiá»ƒm tra viá»‡c Ä‘á»c file, khÃ´ng gá»i API:

```powershell
python scripts\stress_submit_sequences.py `
  --input-dir .\data\stress_sequences `
  --dry-run
```

Biáº¿n mÃ´i trÆ°á»ng há»— trá»£:

- `API_BASE_URL`: URL Serving API, máº·c Ä‘á»‹nh `http://localhost:8000`.

LÆ°u Ã½: script gá»i endpoint CAFA-6 tháº­t thÃ´ng qua Serving API, nÃªn khi tÄƒng `--workers`, `--repeat` hoáº·c sá»‘ file Ä‘áº§u vÃ o thÃ¬ táº£i vÃ  chi phÃ­ phÃ­a endpoint tháº­t cÅ©ng tÄƒng theo.
Note: `--workers` controls concurrency only; `--limit` controls total input records.

Clear request history in dev:

```powershell
python scripts\clear_request_history.py --yes
```
