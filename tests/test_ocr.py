"""Tests for the OCR module."""

import email as email_lib
import io
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

import pytest


# ── availability ──────────────────────────────────────────────────────────────

class TestAvailability:
    def test_is_available_reflects_imports(self):
        from mailclean import ocr
        # is_available() should match _DEPS_AVAILABLE
        assert ocr.is_available() == ocr._DEPS_AVAILABLE

    def test_check_available_raises_when_deps_missing(self):
        with patch('mailclean.ocr._DEPS_AVAILABLE', False):
            from mailclean.ocr import check_available
            with pytest.raises(RuntimeError, match='pip install'):
                check_available()

    def test_check_available_passes_when_deps_present(self):
        with patch('mailclean.ocr._DEPS_AVAILABLE', True):
            from mailclean.ocr import check_available
            check_available()  # should not raise


# ── _ocr_bytes ────────────────────────────────────────────────────────────────

class TestOcrBytes:
    def _inject_mocks(self, mock_pil, mock_tess):
        """Inject PIL and pytesseract mocks into the ocr module namespace."""
        import mailclean.ocr as ocr_mod
        ocr_mod.Image = mock_pil
        ocr_mod.pytesseract = mock_tess

    def _cleanup_mocks(self):
        import mailclean.ocr as ocr_mod
        for attr in ('Image', 'pytesseract'):
            if hasattr(ocr_mod, attr):
                delattr(ocr_mod, attr)

    def test_returns_text_from_image(self):
        import mailclean.ocr as ocr_mod
        mock_pil = MagicMock()
        mock_tess = MagicMock()
        mock_tess.image_to_string.return_value = 'SALE 50% OFF\n'
        self._inject_mocks(mock_pil, mock_tess)
        try:
            with patch.object(ocr_mod, '_DEPS_AVAILABLE', True):
                result = ocr_mod._ocr_bytes(b'PNG_DATA')
        finally:
            self._cleanup_mocks()
        assert result == 'SALE 50% OFF\n'

    def test_returns_empty_on_exception(self):
        import mailclean.ocr as ocr_mod
        mock_pil = MagicMock()
        mock_pil.open.side_effect = Exception("corrupt image")
        mock_tess = MagicMock()
        self._inject_mocks(mock_pil, mock_tess)
        try:
            with patch.object(ocr_mod, '_DEPS_AVAILABLE', True):
                result = ocr_mod._ocr_bytes(b'bad data')
        finally:
            self._cleanup_mocks()
        assert result == ''


# ── extract_text_from_message ─────────────────────────────────────────────────

def _make_multipart_message(text_body: str, image_data: bytes, image_type: str = 'png') -> email_lib.message.Message:
    """Build a minimal multipart email with a text part and an image part."""
    msg = MIMEMultipart()
    msg.attach(MIMEText(text_body, 'plain'))
    img_part = MIMEImage(image_data, _subtype=image_type)
    msg.attach(img_part)
    return msg


class TestExtractTextFromMessage:
    def test_returns_empty_when_deps_missing(self):
        with patch('mailclean.ocr._DEPS_AVAILABLE', False):
            from mailclean.ocr import extract_text_from_message
            msg = MIMEText('hello')
            assert extract_text_from_message(msg) == ''

    def test_extracts_text_from_image_part(self):
        msg = _make_multipart_message('Email body', b'FAKE_PNG')

        with patch('mailclean.ocr._DEPS_AVAILABLE', True), \
             patch('mailclean.ocr._ocr_bytes', return_value='BUY NOW'):
            from mailclean.ocr import extract_text_from_message
            result = extract_text_from_message(msg)

        assert 'BUY NOW' in result

    def test_skips_non_image_parts(self):
        msg = MIMEText('just text')

        with patch('mailclean.ocr._DEPS_AVAILABLE', True), \
             patch('mailclean.ocr._ocr_bytes') as mock_ocr:
            from mailclean.ocr import extract_text_from_message
            extract_text_from_message(msg)

        mock_ocr.assert_not_called()

    def test_skips_empty_image_payloads(self):
        msg = MIMEMultipart()
        img_part = MIMEImage(b'', _subtype='png')
        msg.attach(img_part)

        with patch('mailclean.ocr._DEPS_AVAILABLE', True), \
             patch('mailclean.ocr._ocr_bytes') as mock_ocr:
            from mailclean.ocr import extract_text_from_message
            extract_text_from_message(msg)

        mock_ocr.assert_not_called()

    def test_concatenates_multiple_images(self):
        import mailclean.ocr as ocr_mod
        msg = MIMEMultipart()
        msg.attach(MIMEImage(b'IMG1', _subtype='png'))
        msg.attach(MIMEImage(b'IMG2', _subtype='jpeg'))

        with patch.object(ocr_mod, '_DEPS_AVAILABLE', True), \
             patch.object(ocr_mod, '_ocr_bytes', side_effect=['First image text', 'Second image text']):
            result = ocr_mod.extract_text_from_message(msg)

        assert 'First image text' in result
        assert 'Second image text' in result

    def test_ignores_blank_ocr_output(self):
        msg = _make_multipart_message('body', b'IMG')

        with patch('mailclean.ocr._DEPS_AVAILABLE', True), \
             patch('mailclean.ocr._ocr_bytes', return_value='   \n  '):
            from mailclean.ocr import extract_text_from_message
            result = extract_text_from_message(msg)

        assert result == ''
