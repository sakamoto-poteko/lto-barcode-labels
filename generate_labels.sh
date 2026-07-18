#!/usr/bin/env bash
#
# generate_labels.sh
#
# Generates LTO barcode label sheets using main.py.
#
# By default this produces one mixed-prefix, 30-label sheet on LTO-6 media.
# Override any of the variables below via environment variables, e.g.:
#
#   RANGES_OVERRIDE="BK:31-40 SV:31-50" ./generate_labels.sh
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Activate the project virtualenv if present.
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Ranges are laid out in this order, with each inclusive range sorted from its
# lowest to highest number.
read -r -a RANGES <<< "${RANGES_OVERRIDE:-BK:1-4 TP:1-2 SV:1-14 DK:1-10}"

GENERATION="${GENERATION:-6}"
DIGITS="${DIGITS:-4}"
OUTDIR="${OUTDIR:-output/pdf}"
OUTPUT="${OUTPUT:-${OUTDIR}/mixed_L${GENERATION}_labels.pdf}"

mkdir -p "$OUTDIR"

range_args=()
for label_range in "${RANGES[@]}"; do
  range_args+=(--range "$label_range")
done

echo "Generating ${OUTPUT} (generation=L${GENERATION}, ranges=${RANGES[*]})"
python3 main.py \
  "${range_args[@]}" \
  -g "$GENERATION" \
  -d "$DIGITS" \
  -o "$OUTPUT"

echo "Done. Generated mixed-prefix label sheet: ${OUTPUT}"
