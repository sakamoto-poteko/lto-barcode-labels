# backuplabel

Generate print-ready Code 39 barcode label sheets for IBM LTO-6 cartridges and
Dell TL2000 libraries.

> Vibe-coded in interactive pair-programming sessions between the repo owner
> and Zoo AI coding agents using multiple AI models.

Labels follow the LTO barcode conventions:

- **Label size:** 79.0 mm × 17.0 mm; each black cutter boundary extends to the
  physical paper edges in both directions
- **Symbology:** Code 39, no check digit, standard start/stop
- **Bar geometry:** 11.2 mm high, 0.432 mm narrow element, 2.75:1 ratio
- **Barcode width:** approximately 74.05 mm including 4.3 mm quiet zones
- **Data format:** exactly `PPNNNNL6`
- **Pools:** `SV` (Surveillance), `TP` (Temporary), `DK` (Disks), and `BK`
  (Backups)
- **Human-readable strip:** isolated below the barcode, with a pool-colored
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
python3 main.py -p BK -g 6 -s 1 -d 4 -n 30 -o output/pdf/BK_L6_page1.pdf
```

| Flag | Description |
| --- | --- |
| `-p, --prefix` | Label prefix, e.g. `BK`, `DK`, `SV` (A-Z/0-9 only; `len(prefix) + digits` must equal 6) |
| `-g, --generation` | LTO generation: `5`, `6`, `7`, or `8` |
| `--worm` | Use the WORM suffix instead of Data for the chosen generation |
| `-s, --start` | First serial number |
| `-d, --digits` | Zero-padded width of the serial number |
| `-n, --count` | Total number of labels to generate (spans multiple pages automatically) |
| `-o, --output` | Output PDF path |

## Batch generation script

[`generate_labels.sh`](generate_labels.sh) generates first-page (30-label)
sheets for all four supported prefixes on LTO-6 media by default:

```bash
./generate_labels.sh
```

Override any parameter via environment variables:

```bash
START=31 COUNT=60 PREFIXES_OVERRIDE="BK SV" ./generate_labels.sh
```

## Required samples

Generate one-label sample sheets with:

```bash
for prefix in SV TP DK BK; do
  .venv/bin/python main.py -p "$prefix" -g 6 -s 1 -n 1 \
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
