"""OCR support for extracting text from email image attachments.

Allows body: and text: queries to match text that spammers have hidden
inside images to evade content-based filtering.

Requires optional dependencies:
    pip install mailclean[ocr]

And Tesseract OCR installed on the system:
    macOS:  brew install tesseract
    Debian: apt install tesseract-ocr
    Docs:   https://tesseract-ocr.github.io/tessdoc/Installation.html
"""

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import email.message

try:
    import pytesseract
    from PIL import Image
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False


def is_available() -> bool:
    """Return True if pytesseract and Pillow are installed."""
    return _DEPS_AVAILABLE


def check_available() -> None:
    """Raise RuntimeError with install instructions if OCR deps are missing."""
    if not _DEPS_AVAILABLE:
        raise RuntimeError(
            "OCR requires additional packages:\n"
            "  pip install mailclean[ocr]\n"
            "and Tesseract OCR on your system:\n"
            "  macOS:  brew install tesseract\n"
            "  Debian: apt install tesseract-ocr"
        )


def _ocr_bytes(data: bytes) -> str:
    """Run Tesseract on raw image bytes. Returns extracted text, or '' on failure."""
    try:
        image = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(image)
    except Exception:
        return ''


def extract_text_from_message(msg: 'email.message.Message') -> str:
    """
    Walk all MIME parts of a parsed email and run OCR on every image part found.

    Returns the concatenated OCR text from all images, separated by newlines.
    Returns '' if no images are found, OCR fails, or deps are not installed.
    """
    if not _DEPS_AVAILABLE:
        return ''

    parts = []
    for part in msg.walk():
        if not part.get_content_type().startswith('image/'):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        text = _ocr_bytes(payload)
        if text.strip():
            parts.append(text.strip())

    return '\n'.join(parts)
