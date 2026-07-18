# backuplabel

Generate print-ready Code 39 barcode label sheets for LTO tape cartridges
(LTO-5 through LTO-8, Data and WORM), compatible with IBM/Dell TL2000/TL4000,
HP MSL, Quantum, and similar tape libraries.

> Vibe-coded in an interactive pair-programming session between the repo
> owner and the Zoo AI coding agent (Claude Sonnet).

Labels follow the LTO barcode conventions:

- **Label size:** 67.5 mm × 17.0 mm, square corners
- **Symbology:** Code 39, no check digit, standard start/stop
- **Bar height:** 8.0 mm, narrow bar 0.25 mm (10 mil), 3:1 wide:narrow ratio
- **Quiet zone:** 3.5 mm (above the 2.5 mm spec minimum, for extra scanner tolerance)
- **Data format:** exactly 8 visible characters, `VVVVVVMT`
  (6-character VOLSER + 2-character media suffix)
- **Media suffix** is derived automatically from the LTO generation you choose
  (`L5/LV`, `L6/LW`, `L7/LX`, `L8/LY`) — it cannot be typed directly.
- **VOLSER characters** are restricted to `A-Z` / `0-9` (no lowercase, spaces,
  or punctuation).

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

[`generate_labels.sh`](generate_labels.sh) generates the first-page (30-label)
sheets for the `BK`, `DK`, and `SV` prefixes on LTO-6 media by default:

```bash
./generate_labels.sh
```

Override any parameter via environment variables:

```bash
GENERATION=7 DIGITS=5 COUNT=60 PREFIXES_OVERRIDE="BK DK SV EXTRA" ./generate_labels.sh
```

## Font

The numeric portion of the human-readable text uses the real Monaco
typeface (`/System/Library/Fonts/Monaco.ttf` on macOS), embedded directly
into the PDF at regular weight (Monaco has no bold face). On systems where
Monaco isn't available, it falls back to the built-in Courier font.
