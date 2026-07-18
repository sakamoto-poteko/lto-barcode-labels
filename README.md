# backuplabel

Generate print-ready Code 39 barcode label sheets for IBM LTO-6 cartridges and
Dell TL2000 libraries.

> Vibe-coded in interactive pair-programming sessions between the repo owner
> and Zoo AI coding agents using multiple AI models.

Labels follow the LTO barcode conventions:

- **Label size:** 79.0 mm × 17.0 mm; each black cutter boundary extends to the
  physical paper edges in both directions
- **Symbology:** Code 39, no check digit, standard start/stop
- **Bar geometry:** 11.8 mm high, 0.432 mm narrow element, 2.75:1 ratio; the
  taller bars remain inside the existing 79.0 mm × 17.0 mm label boundary
- **Barcode width:** approximately 74.05 mm including 4.3 mm quiet zones
- **Data format:** exactly `PPNNNNL6`
- **Pools:** `SV` (Surveillance), `TP` (Temporary), `DK` (Disks), and `BK`
  (Backups)
- **Human-readable strip:** positioned above the barcode, with a pool-colored
  prefix, four separately colored digit cells, and a neutral `L6` cell
- **Zero treatment:** light cyan `#8ECAD6` with black text and white separation,
  preventing repeated zeroes from becoming a dark visual mass

## Requirements

- Python 3.9+
- [reportlab](https://pypi.org/project/reportlab/)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python3 main.py -g 6 -d 4 \
  -r BK:1-4 -r TP:1-2 -r SV:1-14 -r DK:1-10 \
  -o output/pdf/mixed_L6_labels.pdf
```

| Flag | Description |
| --- | --- |
| `-r, --range` | Inclusive `PREFIX:START-END` range; repeat to combine prefixes. Ranges retain command-line order and numbers are laid out from low to high. |
| `-g, --generation` | LTO generation (currently fixed at `6`) |
| `-d, --digits` | Zero-padded serial width (currently fixed at `4`) |
| `-o, --output` | Output PDF path |

## Batch generation script

[`generate_labels.sh`](generate_labels.sh) generates one 30-label LTO-6 page:
`BK` 1–4, `TP` 1–2, `SV` 1–14, followed by `DK` 1–10.

```bash
./generate_labels.sh
```

Override any parameter via environment variables:

```bash
RANGES_OVERRIDE="BK:31-40 SV:31-50" ./generate_labels.sh
```

## Required samples

Generate one-label sample sheets with:

```bash
for prefix in SV TP DK BK; do
  .venv/bin/python main.py -g 6 -r "$prefix:1-1" \
    -o "output/samples/${prefix}0001L6.pdf"
done
```

The resulting PDFs are `SV0001L6`, `TP0001L6`, `DK0001L6`, and `BK0001L6`.
Print PDFs at **100% / Actual Size** on matte white polyester stock; disable
printer scaling and do not laminate.

## Font

The numeric portion of the human-readable text uses the real Monaco
typeface (`/System/Library/Fonts/Monaco.ttf` on macOS), embedded directly
into the PDF at regular weight (Monaco has no bold face). On systems where
Monaco isn't available, it falls back to the built-in Courier font.
