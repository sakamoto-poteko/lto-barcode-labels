#!/usr/bin/env bash
#
# generate_labels.sh
#
# Generates LTO barcode label sheets using main.py.
#
# By default this produces the first-page (30-label) sheets for the SV, TP,
# DK, and BK prefixes on LTO-6 media, matching the revised label
# Specification. Override any of the variables below via environment
# variables, e.g.:
#
#   GENERATION=7 DIGITS=5 COUNT=60 ./generate_labels.sh
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Activate the project virtualenv if present.
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Allow PREFIXES_OVERRIDE="SV TP DK BK" to expand to multiple words.
read -r -a PREFIXES <<< "${PREFIXES_OVERRIDE:-SV TP DK BK}"

GENERATION="${GENERATION:-6}"
START="${START:-1}"
DIGITS="${DIGITS:-4}"
COUNT="${COUNT:-30}"
OUTDIR="${OUTDIR:-output/pdf}"

mkdir -p "$OUTDIR"

for prefix in "${PREFIXES[@]}"; do
  out="${OUTDIR}/${prefix}_L${GENERATION}_page1.pdf"
  echo "Generating ${out} (prefix=${prefix}, generation=L${GENERATION}, start=${START}, digits=${DIGITS}, count=${COUNT})"
  python3 main.py \
    -p "$prefix" \
    -g "$GENERATION" \
    -s "$START" \
    -d "$DIGITS" \
    -n "$COUNT" \
    -o "$out"
done

echo "Done. Generated ${#PREFIXES[@]} label sheet(s) in ${OUTDIR}/"
