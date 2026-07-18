import argparse
import math
import re
from pathlib import Path

from reportlab.graphics.barcode.code39 import Standard39
from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


DEFAULT_OUTPUT = Path("output/pdf/labels.pdf")

# ---------------------------------------------------------------------------
# Layout configuration
# ---------------------------------------------------------------------------
LABEL_WIDTH = 67.5 * mm
LABEL_HEIGHT = 17.0 * mm
BAR_HEIGHT = 8.0 * mm
NARROW_BAR = 0.254 * mm  # 10 mil

# Spec minimum is 2.5 mm. We use a larger value to give scanners extra
# tolerance/safety margin while still fitting comfortably inside the
# 67.5 mm label width (verified at draw time, see draw_label()).
QUIET_ZONE = 3.5 * mm

COLS = 2
ROWS = 15
H_GAP = 10.0 * mm
V_GAP = 1.0 * mm
LABELS_PER_PAGE = COLS * ROWS

# ---------------------------------------------------------------------------
# Data-format configuration
# ---------------------------------------------------------------------------
# Total visible characters must always be exactly 8: VVVVVVMT
# (6-char VOLSER + 2-char media suffix).
TOTAL_VISIBLE_CHARS = 8
MEDIA_SUFFIX_LEN = 2
VOLSER_LEN = TOTAL_VISIBLE_CHARS - MEDIA_SUFFIX_LEN  # 6

# VOLSER characters (prefix + zero-padded number) may only be A-Z / 0-9.
VOLSER_CHAR_RE = re.compile(r"^[A-Z0-9]+$")

# Media suffix is derived from the LTO generation number; the user may not
# type an arbitrary suffix directly, only the generation (and optional
# WORM flag). index 0 = Data cartridge, index 1 = WORM.
GENERATION_SUFFIXES: dict[int, tuple[str, str]] = {
    5: ("L5", "LV"),
    6: ("L6", "LW"),
    7: ("L7", "LX"),
    8: ("L8", "LY"),
}

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
    global NUMBER_FONT, _fonts_registered
    if _fonts_registered:
        return
    for candidate in _MONACO_TTF_CANDIDATES:
        if candidate.exists():
            pdfmetrics.registerFont(TTFont("Monaco", str(candidate)))
            NUMBER_FONT = "Monaco"
            break
    else:
        NUMBER_FONT = "Courier"
    _fonts_registered = True


# ---------------------------------------------------------------------------
# Text style configuration
# ---------------------------------------------------------------------------
TEXT_FONT_SIZE = 8.5      # prefix / media font size
NUMBER_FONT_SIZE = 12.0   # numbers are the primary read, so make them larger

# Prefix: bold sans-serif in a distinct color so it's easily told apart
# from the number even though it's already alphabetic.
PREFIX_FONT = "Helvetica-Bold"
PREFIX_COLOR = Color(0.05, 0.25, 0.55)  # dark blue

# Number: fixed-width font, larger size, black - the main identifier at a
# glance, so digits always line up and stand out from prefix/media text.
# NUMBER_FONT itself is set by register_fonts() (embedded Monaco or a
# Courier fallback).
NUMBER_COLOR = black

# Media label (e.g. "L6"): distinct color so it's clearly told apart from
# the numeric portion of the code.
MEDIA_FONT = "Helvetica-Bold"
MEDIA_COLOR = Color(0.72, 0.30, 0.05)  # burnt orange


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a sheet of Code 39 barcode labels."
    )
    parser.add_argument(
        "-p", "--prefix",
        required=True,
        help="Label prefix, e.g. BK for Backup, DK for Disk, SV for Surveillance "
             "(A-Z/0-9 only; prefix length + --digits must equal 6)",
    )
    parser.add_argument(
        "-g", "--generation",
        type=int,
        required=True,
        choices=sorted(GENERATION_SUFFIXES),
        help="LTO generation number: 5, 6, 7, or 8. The media suffix "
             "(e.g. L6/LW) is derived automatically, not typed directly.",
    )
    parser.add_argument(
        "--worm",
        action="store_true",
        help="Use the WORM media suffix instead of the Data suffix "
             "for the chosen generation.",
    )
    parser.add_argument(
        "-s", "--start",
        type=int,
        required=True,
        help="First number to use",
    )
    parser.add_argument(
        "-d", "--digits",
        type=int,
        required=True,
        help="Zero-padded width of the number, e.g. 4 -> 0001",
    )
    parser.add_argument(
        "-n", "--count",
        type=int,
        required=True,
        help="Total number of labels to generate, may span multiple pages",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output PDF path (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


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
    if len(normalized) + digits != VOLSER_LEN:
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

    # A very light exact-size cutting guide; the barcode itself is pure black.
    canvas.saveState()
    canvas.setStrokeColor(Color(0.78, 0.78, 0.78))
    canvas.setLineWidth(0.2)
    canvas.rect(x, y, LABEL_WIDTH, LABEL_HEIGHT, stroke=1, fill=0)
    canvas.restoreState()

    barcode = Standard39(
        barcode_value,
        checksum=0,
        stop=1,
        humanReadable=0,
        barWidth=NARROW_BAR,
        barHeight=BAR_HEIGHT,
        ratio=3.0,
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
    barcode_y = y + LABEL_HEIGHT - 1.5 * mm - BAR_HEIGHT
    barcode.drawOn(canvas, barcode_x, barcode_y)

    # Human-readable text, drawn as three separately styled segments
    # (prefix / number / media) so each part can use its own font and
    # color while still lining up as one continuous, centered string.
    canvas.saveState()

    w_prefix = canvas.stringWidth(prefix, PREFIX_FONT, TEXT_FONT_SIZE)
    w_number = canvas.stringWidth(number_str, NUMBER_FONT, NUMBER_FONT_SIZE)
    w_media = canvas.stringWidth(media, MEDIA_FONT, TEXT_FONT_SIZE)
    total_width = w_prefix + w_number + w_media

    text_x = x + (LABEL_WIDTH - total_width) / 2
    # Baselines are offset slightly so the larger number text stays
    # visually centered against the smaller prefix/media text.
    base_y = y + 3.7 * mm
    small_y = base_y
    large_y = base_y - (NUMBER_FONT_SIZE - TEXT_FONT_SIZE) * 0.22

    canvas.setFont(PREFIX_FONT, TEXT_FONT_SIZE)
    canvas.setFillColor(PREFIX_COLOR)
    canvas.drawString(text_x, small_y, prefix)
    text_x += w_prefix

    canvas.setFont(NUMBER_FONT, NUMBER_FONT_SIZE)
    canvas.setFillColor(NUMBER_COLOR)
    canvas.drawString(text_x, large_y, number_str)
    text_x += w_number

    canvas.setFont(MEDIA_FONT, TEXT_FONT_SIZE)
    canvas.setFillColor(MEDIA_COLOR)
    canvas.drawString(text_x, small_y, media)

    canvas.restoreState()


def generate_labels_pdf(
    prefix: str,
    generation: int,
    worm: bool,
    start: int,
    digits: int,
    count: int,
    output: Path,
) -> Path:
    """Validate inputs and render a full label sheet PDF.

    The media suffix is always derived from `generation` (+ `worm`); the
    caller may never supply an arbitrary suffix directly.
    """
    if generation not in GENERATION_SUFFIXES:
        raise SystemExit(
            f"Unsupported LTO generation: {generation}. "
            f"Supported: {sorted(GENERATION_SUFFIXES)}"
        )

    prefix = validate_label_format(prefix, digits)
    validate_number_range(start, count, digits)
    media = GENERATION_SUFFIXES[generation][1 if worm else 0]

    register_fonts()

    output.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = A4
    grid_width = COLS * LABEL_WIDTH + (COLS - 1) * H_GAP
    grid_height = ROWS * LABEL_HEIGHT + (ROWS - 1) * V_GAP
    left = (page_width - grid_width) / 2
    bottom = (page_height - grid_height) / 2

    canvas = Canvas(str(output), pagesize=A4, pageCompression=1)
    canvas.setTitle(f"{prefix} {media} Barcode Labels")
    canvas.setAuthor("OpenAI Codex")

    total_pages = max(1, math.ceil(count / LABELS_PER_PAGE))
    number = start

    for page in range(total_pages):
        labels_on_this_page = min(LABELS_PER_PAGE, count - page * LABELS_PER_PAGE)

        index = 0
        for row in range(ROWS):
            y = bottom + (ROWS - 1 - row) * (LABEL_HEIGHT + V_GAP)
            for col in range(COLS):
                if index >= labels_on_this_page:
                    break
                x = left + col * (LABEL_WIDTH + H_GAP)
                draw_label(canvas, x, y, number, prefix, media, digits)
                number += 1
                index += 1

        canvas.showPage()

    canvas.save()
    return output


def main() -> None:
    args = parse_args()
    generate_labels_pdf(
        prefix=args.prefix,
        generation=args.generation,
        worm=args.worm,
        start=args.start,
        digits=args.digits,
        count=args.count,
        output=args.output,
    )


if __name__ == "__main__":
    main()
