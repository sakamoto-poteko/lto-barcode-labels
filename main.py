import argparse
import math
import re
from pathlib import Path

from reportlab.graphics.barcode.code39 import Standard39
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


DEFAULT_OUTPUT = Path("output/pdf/labels.pdf")

# ---------------------------------------------------------------------------
# Layout configuration
# ---------------------------------------------------------------------------
# Revised IBM/Dell LTO-6 label geometry.  All dimensions remain in points
# internally, but are declared in millimetres so the PDF prints at exact size.
LABEL_WIDTH = 79.0 * mm
LABEL_HEIGHT = 17.0 * mm
BAR_HEIGHT = 11.8 * mm  # fills all space above the human-readable strip
NARROW_BAR = 0.432 * mm  # 17 mil nominal (IBM spec, not 10 mil)
WIDE_NARROW_RATIO = 2.75
QUIET_ZONE = 4.3 * mm
BARCODE_BOTTOM_MARGIN = 0.2 * mm

# The strip is wholly above the bars. Its bottom meets the top of the bars;
# no vertical gap is needed between the two regions.
STRIP_BOTTOM = BARCODE_BOTTOM_MARGIN + BAR_HEIGHT
STRIP_HEIGHT = 4.5 * mm
PREFIX_CELL_WIDTH = 7.5 * mm
DIGIT_CELL_WIDTH = 4.5 * mm
MEDIA_CELL_WIDTH = 7.5 * mm
CELL_GAP = 2.5 * mm
PREFIX_GAP = 4.5 * mm
MEDIA_GAP = 4.5 * mm
MEDIA_BORDER_WIDTH = 0.12 * mm
LABEL_GUIDE_COLOR = black
LABEL_GUIDE_WIDTH = 0.10 * mm

# Labels are cut consecutively from a continuous strip, not individually,
# so there is no gap between adjacent labels in either direction.
COLS = 2
ROWS = 15
H_GAP = 0.0 * mm
V_GAP = 0.0 * mm
LABELS_PER_PAGE = COLS * ROWS

# ---------------------------------------------------------------------------
# Data-format configuration
# ---------------------------------------------------------------------------
# Total visible characters must always be exactly 8: PPNNNNL6.
TOTAL_VISIBLE_CHARS = 8
MEDIA_SUFFIX_LEN = 2
VOLSER_LEN = TOTAL_VISIBLE_CHARS - MEDIA_SUFFIX_LEN  # 6
SERIAL_DIGITS = 4
MEDIA_SUFFIX = "L6"
SUPPORTED_PREFIXES = {"SV", "TP", "DK", "BK"}

# VOLSER characters (prefix + zero-padded number) may only be A-Z / 0-9.
VOLSER_CHAR_RE = re.compile(r"^[A-Z0-9]+$")

# Media suffix is derived from the LTO generation number; the user may not
# type an arbitrary suffix directly, only the generation (and optional
# WORM flag). index 0 = Data cartridge, index 1 = WORM.
GENERATION_SUFFIXES: dict[int, tuple[str, str]] = {6: (MEDIA_SUFFIX, MEDIA_SUFFIX)}

# ---------------------------------------------------------------------------
# Font embedding (Monaco, regular weight only - macOS has no Monaco-Bold)
# ---------------------------------------------------------------------------
NUMBER_FONT = "Monaco"
_MONACO_TTF_CANDIDATES = [
    Path("/System/Library/Fonts/Monaco.ttf"),  # macOS
]
_fonts_registered = False


def register_fonts() -> None:
    """Embed Monaco (regular) for the numeric portion of the label.

    Falls back to the built-in Courier font if Monaco isn't available on
    this system, so label generation still succeeds elsewhere.
    """
    global NUMBER_FONT, PREFIX_FONT, MEDIA_FONT, _fonts_registered
    if _fonts_registered:
        return
    for candidate in _MONACO_TTF_CANDIDATES:
        if candidate.exists():
            pdfmetrics.registerFont(TTFont("Monaco", str(candidate)))
            NUMBER_FONT = "Monaco"
            break
    else:
        NUMBER_FONT = "Courier"
    PREFIX_FONT = NUMBER_FONT
    MEDIA_FONT = NUMBER_FONT
    _fonts_registered = True


# ---------------------------------------------------------------------------
# Text style configuration
# ---------------------------------------------------------------------------
TEXT_FONT_SIZE = 14.0
NUMBER_FONT_SIZE = 14.0

# The complete human-readable identifier uses the existing selected Monaco
# face (or the same Courier fallback) for consistent optical centring.
PREFIX_FONT = NUMBER_FONT
PREFIX_COLORS = {
    "SV": HexColor("#B71C1C"),
    "TP": HexColor("#EF6C00"),
    "DK": HexColor("#1565C0"),
    "BK": HexColor("#2E7D32"),
}

# Number: fixed-width font, larger size, black - the main identifier at a
# glance, so digits always line up and stand out from prefix/media text.
# NUMBER_FONT itself is set by register_fonts() (embedded Monaco or a
# Courier fallback).
DIGIT_STYLES = {
    "0": (HexColor("#8ECAD6"), black),
    "1": (HexColor("#D95C5C"), white),
    "2": (HexColor("#5FAE6B"), white),
    "3": (HexColor("#5B86C5"), white),
    "4": (HexColor("#D99045"), black),
    "5": (HexColor("#8A6BBE"), white),
    "6": (HexColor("#4F9C9C"), white),
    "7": (HexColor("#D6B94C"), black),
    "8": (HexColor("#8A8A8A"), white),
    "9": (HexColor("#E5B4C2"), black),
}

MEDIA_FONT = NUMBER_FONT
MEDIA_BORDER_COLOR = HexColor("#D7D7D7")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a sheet of Code 39 barcode labels."
    )
    parser.add_argument(
        "-r", "--range",
        dest="ranges",
        action="append",
        required=True,
        metavar="PREFIX:START-END",
        help=(
            "Prefix and inclusive number range; repeat to place multiple "
            "prefixes on the same sheet (for example, -r BK:1-4 -r TP:1-2)"
        ),
    )
    parser.add_argument(
        "-g", "--generation",
        type=int,
        required=True,
        choices=[6],
        help="LTO generation number (this design supports LTO-6)",
    )
    parser.add_argument(
        "--worm",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-d", "--digits",
        type=int,
        default=SERIAL_DIGITS,
        choices=[SERIAL_DIGITS],
        help="Serial width (fixed at 4; default: 4)",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output PDF path (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def parse_label_ranges(args: argparse.Namespace) -> list[tuple[str, int]]:
    """Expand CLI ranges into labels, preserving the user's range order."""
    labels: list[tuple[str, int]] = []
    range_re = re.compile(r"^([A-Za-z0-9]+):(\d+)-(\d+)$")
    for value in args.ranges:
        match = range_re.fullmatch(value)
        if not match:
            raise SystemExit(
                f"Invalid range {value!r}; expected PREFIX:START-END "
                "(for example, BK:1-4)."
            )
        raw_prefix, raw_start, raw_end = match.groups()
        prefix = validate_label_format(raw_prefix, args.digits)
        start, end = int(raw_start), int(raw_end)
        if end < start:
            raise SystemExit(
                f"Invalid range {value!r}: END must be greater than or equal to START."
            )
        validate_number_range(start, end - start + 1, args.digits)
        labels.extend((prefix, number) for number in range(start, end + 1))
    return labels


def validate_label_format(prefix: str, digits: int) -> str:
    """Validate VOLSER character set and length, returning the normalized
    (upper-cased) prefix.

    Enforces:
      - only A-Z / 0-9 characters (spec: no lowercase/spaces/punctuation)
      - prefix length + digits == 6, so the full VVVVVVMT string is always
        exactly 8 visible characters.
    """
    normalized = prefix.upper()
    if not VOLSER_CHAR_RE.match(normalized):
        raise SystemExit(
            f"Invalid prefix {prefix!r}: VOLSER may only contain A-Z and 0-9 "
            "(no lowercase, spaces, or punctuation)."
        )
    if normalized not in SUPPORTED_PREFIXES:
        raise SystemExit(
            f"Unsupported prefix {normalized!r}; choose one of "
            f"{', '.join(sorted(SUPPORTED_PREFIXES))}."
        )
    if len(normalized) != 2 or digits != SERIAL_DIGITS:
        raise SystemExit(
            f"Invalid format: prefix ({len(normalized)} chars) + digits "
            f"({digits}) must total exactly {VOLSER_LEN} characters "
            f"(VOLSER length), got {len(normalized) + digits}. The full "
            f"label must be exactly {TOTAL_VISIBLE_CHARS} characters "
            "(VOLSER + 2-char media suffix)."
        )
    return normalized


def validate_number_range(start: int, count: int, digits: int) -> None:
    """Ensure every generated number fits within the configured digit width."""
    if start < 0:
        raise SystemExit("--start must be non-negative.")
    if count < 1:
        raise SystemExit("--count must be at least 1.")
    max_number = start + count - 1
    if len(str(max_number)) > digits:
        raise SystemExit(
            f"Number range overflow: highest number {max_number} needs "
            f"{len(str(max_number))} digits, but --digits={digits}."
        )


def format_value(number: int, prefix: str, media: str, digits: int) -> tuple[str, str, str]:
    """Return the (prefix, number, media) text parts for a given number."""
    number_str = str(number).zfill(digits)
    return prefix, number_str, media


def _draw_centered_text(
    canvas: Canvas,
    text: str,
    center_x: float,
    cell_y: float,
    cell_height: float,
    font: str,
    size: float,
    color,
) -> None:
    """Draw text optically centred in a fixed-height cell."""
    # These labels contain only capitals and digits.  Centre their visible
    # cap-height rather than the full font em-box (which includes invisible
    # ascender/descender allowance and makes glyphs look vertically offset).
    # A 0.70 em cap-height matches Helvetica/Courier/Monaco closely and avoids
    # relying on backend-specific font-face internals.
    cap_height = size * 0.70
    baseline = cell_y + (cell_height - cap_height) / 2
    canvas.setFont(font, size)
    canvas.setFillColor(color)
    canvas.drawCentredString(center_x, baseline, text)


def draw_human_readable_strip(
    canvas: Canvas,
    x: float,
    y: float,
    prefix: str,
    number_str: str,
    media: str,
) -> None:
    """Render PP | N | N | N | N | L6 above the barcode only."""
    strip_width = (
        PREFIX_CELL_WIDTH
        + len(number_str) * DIGIT_CELL_WIDTH
        + (len(number_str) - 1) * CELL_GAP
        + PREFIX_GAP
        + MEDIA_GAP
        + MEDIA_CELL_WIDTH
    )
    # Centre the complete identifier as one unit within the physical label;
    # each glyph is then independently centred within its own cell.
    cell_x = x + (LABEL_WIDTH - strip_width) / 2
    cell_y = y + STRIP_BOTTOM

    canvas.saveState()
    canvas.setFillColor(PREFIX_COLORS[prefix])
    canvas.rect(cell_x, cell_y, PREFIX_CELL_WIDTH, STRIP_HEIGHT, stroke=0, fill=1)
    _draw_centered_text(
        canvas, prefix, cell_x + PREFIX_CELL_WIDTH / 2, cell_y, STRIP_HEIGHT,
        PREFIX_FONT, TEXT_FONT_SIZE, white,
    )
    cell_x += PREFIX_CELL_WIDTH + PREFIX_GAP

    for digit in number_str:
        background, foreground = DIGIT_STYLES[digit]
        canvas.setFillColor(background)
        canvas.rect(cell_x, cell_y, DIGIT_CELL_WIDTH, STRIP_HEIGHT, stroke=0, fill=1)
        _draw_centered_text(
            canvas, digit, cell_x + DIGIT_CELL_WIDTH / 2, cell_y, STRIP_HEIGHT,
            NUMBER_FONT, NUMBER_FONT_SIZE, foreground,
        )
        cell_x += DIGIT_CELL_WIDTH + CELL_GAP

    # Replace the ordinary post-digit separator with the larger media gap.
    cell_x += MEDIA_GAP - CELL_GAP
    canvas.setFillColor(white)
    canvas.setStrokeColor(MEDIA_BORDER_COLOR)
    canvas.setLineWidth(MEDIA_BORDER_WIDTH)
    canvas.rect(cell_x, cell_y, MEDIA_CELL_WIDTH, STRIP_HEIGHT, stroke=1, fill=1)
    _draw_centered_text(
        canvas, media, cell_x + MEDIA_CELL_WIDTH / 2, cell_y, STRIP_HEIGHT,
        MEDIA_FONT, TEXT_FONT_SIZE, black,
    )
    canvas.restoreState()


def draw_label(
    canvas: Canvas,
    x: float,
    y: float,
    number: int,
    prefix: str,
    media: str,
    digits: int,
) -> None:
    prefix, number_str, media = format_value(number, prefix, media, digits)
    barcode_value = f"{prefix}{number_str}{media}"

    # Paint the exact label area white.  Cutter lines are drawn page-wide by
    # draw_cutting_grid(), rather than stopping at individual label corners.
    canvas.saveState()
    canvas.setFillColor(white)
    canvas.rect(x, y, LABEL_WIDTH, LABEL_HEIGHT, stroke=0, fill=1)
    canvas.restoreState()

    barcode = Standard39(
        barcode_value,
        checksum=0,
        stop=1,
        humanReadable=0,
        barWidth=NARROW_BAR,
        barHeight=BAR_HEIGHT,
        ratio=WIDE_NARROW_RATIO,
        quiet=1,
        lquiet=QUIET_ZONE,
        rquiet=QUIET_ZONE,
    )

    if barcode.width > LABEL_WIDTH:
        raise ValueError(
            f"Barcode width {barcode.width / mm:.2f}mm exceeds label width "
            f"{LABEL_WIDTH / mm:.2f}mm for value {barcode_value!r}; "
            "reduce QUIET_ZONE or NARROW_BAR."
        )

    barcode_x = x + (LABEL_WIDTH - barcode.width) / 2
    barcode_y = y + BARCODE_BOTTOM_MARGIN
    barcode.drawOn(canvas, barcode_x, barcode_y)

    draw_human_readable_strip(canvas, x, y, prefix, number_str, media)


def draw_cutting_grid(
    canvas: Canvas,
    left: float,
    bottom: float,
    page_width: float,
    page_height: float,
) -> None:
    """Extend every label boundary to the physical edges of the paper."""
    canvas.saveState()
    canvas.setStrokeColor(LABEL_GUIDE_COLOR)
    canvas.setLineWidth(LABEL_GUIDE_WIDTH)
    canvas.setDash([])

    for col in range(COLS + 1):
        guide_x = left + col * LABEL_WIDTH
        canvas.line(guide_x, 0, guide_x, page_height)

    for row in range(ROWS + 1):
        guide_y = bottom + row * LABEL_HEIGHT
        canvas.line(0, guide_y, page_width, guide_y)

    canvas.restoreState()


def generate_labels_pdf(
    labels: list[tuple[str, int]],
    generation: int,
    worm: bool,
    digits: int,
    output: Path,
) -> Path:
    """Validate inputs and render ordered labels to one or more PDF pages.

    The media suffix is always derived from `generation` (+ `worm`); the
    caller may never supply an arbitrary suffix directly.
    """
    if generation not in GENERATION_SUFFIXES:
        raise SystemExit(
            f"Unsupported LTO generation: {generation}. "
            f"Supported: {sorted(GENERATION_SUFFIXES)}"
        )

    if not labels:
        raise SystemExit("At least one label is required.")
    for prefix, number in labels:
        validate_label_format(prefix, digits)
        validate_number_range(number, 1, digits)
    if worm:
        raise SystemExit("WORM media is not supported by the PPNNNNL6 design.")
    media = MEDIA_SUFFIX

    register_fonts()

    output.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = A4
    grid_width = COLS * LABEL_WIDTH + (COLS - 1) * H_GAP
    grid_height = ROWS * LABEL_HEIGHT + (ROWS - 1) * V_GAP
    left = (page_width - grid_width) / 2
    bottom = (page_height - grid_height) / 2

    canvas = Canvas(str(output), pagesize=A4, pageCompression=1)
    canvas.setTitle(f"Mixed-prefix {media} Barcode Labels")
    canvas.setAuthor("OpenAI Codex")

    total_pages = math.ceil(len(labels) / LABELS_PER_PAGE)

    for page in range(total_pages):
        page_labels = labels[
            page * LABELS_PER_PAGE:(page + 1) * LABELS_PER_PAGE
        ]

        index = 0
        for row in range(ROWS):
            y = bottom + (ROWS - 1 - row) * (LABEL_HEIGHT + V_GAP)
            for col in range(COLS):
                if index >= len(page_labels):
                    break
                x = left + col * (LABEL_WIDTH + H_GAP)
                prefix, number = page_labels[index]
                draw_label(canvas, x, y, number, prefix, media, digits)
                index += 1

        draw_cutting_grid(canvas, left, bottom, page_width, page_height)
        canvas.showPage()

    canvas.save()
    return output


def main() -> None:
    args = parse_args()
    generate_labels_pdf(
        labels=parse_label_ranges(args),
        generation=args.generation,
        worm=args.worm,
        digits=args.digits,
        output=args.output,
    )


if __name__ == "__main__":
    main()
