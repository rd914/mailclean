"""Tests for the IMAP client."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import email
from email.mime.text import MIMEText

from mailclean.imap_client import IMAPClient, IMAPError, MAILCLEAN_DELETED_FOLDER


class TestIMAPClient:
    """Tests for the IMAPClient class."""

    def test_init(self):
        """Test client initialization."""
        client = IMAPClient(
            server="imap.example.com",
            port=993,
            email_addr="user@example.com",
            password="password",
        )

        assert client.server == "imap.example.com"
        assert client.port == 993
        assert client.email_addr == "user@example.com"
        assert client.use_ssl is True

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_connect_success(self, mock_imap_class):
        """Test successful connection."""
        mock_imap = Mock()
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()

        mock_imap_class.assert_called_once_with("imap.example.com", 993)
        mock_imap.login.assert_called_once_with("user@example.com", "password")

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_connect_failure(self, mock_imap_class):
        """Test connection failure."""
        import imaplib
        mock_imap = Mock()
        mock_imap.login.side_effect = imaplib.IMAP4.error("Login failed")
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")

        with pytest.raises(IMAPError):
            client.connect()

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_list_folders(self, mock_imap_class):
        """Test listing folders."""
        mock_imap = Mock()
        mock_imap.list.return_value = ('OK', [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren) "/" "Sent"',
            b'(\\HasNoChildren) "/" "Drafts"',
        ])
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()
        folders = client.list_folders()

        assert "INBOX" in folders
        assert "Sent" in folders
        assert "Drafts" in folders

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_select_folder(self, mock_imap_class):
        """Test selecting a folder."""
        mock_imap = Mock()
        mock_imap.select.return_value = ('OK', [b'42'])
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()
        count = client.select_folder("INBOX")

        assert count == 42
        mock_imap.select.assert_called_with("INBOX")

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_search_uids(self, mock_imap_class):
        """Test searching for message UIDs."""
        mock_imap = Mock()
        mock_imap.select.return_value = ('OK', [b'100'])
        mock_imap.uid.return_value = ('OK', [b'1 2 3 4 5'])
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()
        client.select_folder("INBOX")
        uids = client.search_uids("ALL")

        assert uids == [1, 2, 3, 4, 5]

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_search_uids_empty(self, mock_imap_class):
        """Test searching with no results."""
        mock_imap = Mock()
        mock_imap.select.return_value = ('OK', [b'0'])
        mock_imap.uid.return_value = ('OK', [b''])
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()
        client.select_folder("INBOX")
        uids = client.search_uids("ALL")

        assert uids == []

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_context_manager(self, mock_imap_class):
        """Test using client as context manager."""
        mock_imap = Mock()
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")

        with client.connection():
            pass

        mock_imap.login.assert_called_once()
        mock_imap.logout.assert_called_once()

    def test_check_connection_not_connected(self):
        """Test that operations fail when not connected."""
        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")

        with pytest.raises(IMAPError):
            client.list_folders()

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_create_folder(self, mock_imap_class):
        """Test creating a folder."""
        mock_imap = Mock()
        mock_imap.create.return_value = ('OK', [])
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()
        client.create_folder("NewFolder")

        mock_imap.create.assert_called_with("NewFolder")

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_ensure_mailclean_folder_creates(self, mock_imap_class):
        """Test that MailClean-Deleted folder is created if missing."""
        mock_imap = Mock()
        mock_imap.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "INBOX"'])
        mock_imap.create.return_value = ('OK', [])
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()
        client.ensure_mailclean_folder()

        mock_imap.create.assert_called_with(MAILCLEAN_DELETED_FOLDER)

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_ensure_mailclean_folder_exists(self, mock_imap_class):
        """Test that MailClean-Deleted folder is not recreated if it exists."""
        mock_imap = Mock()
        mock_imap.list.return_value = ('OK', [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren) "/" "MailClean-Deleted"',
        ])
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()
        client.ensure_mailclean_folder()

        mock_imap.create.assert_not_called()


class TestEmailParsing:
    """Tests for email parsing functionality."""

    def create_raw_email(
        self,
        from_addr: str = "sender@example.com",
        to_addr: str = "recipient@example.com",
        subject: str = "Test Subject",
        body: str = "Test body",
        date: str = "Mon, 15 Jun 2024 10:30:00 +0000",
    ) -> bytes:
        """Create a raw email message."""
        msg = MIMEText(body)
        msg['From'] = from_addr
        msg['To'] = to_addr
        msg['Subject'] = subject
        msg['Date'] = date
        msg['Message-ID'] = '<test123@example.com>'
        return msg.as_bytes()

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_fetch_email(self, mock_imap_class):
        """Test fetching and parsing an email."""
        raw_email = self.create_raw_email()

        mock_imap = Mock()
        mock_imap.select.return_value = ('OK', [b'100'])
        mock_imap.uid.return_value = ('OK', [(b'1 (UID 1 RFC822.HEADER {100}', raw_email), b')'])
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()
        client.select_folder("INBOX")
        email_msg = client.fetch_email(1, include_body=False)

        assert email_msg is not None
        assert email_msg.from_address == "sender@example.com"
        assert "recipient@example.com" in email_msg.to_addresses
        assert email_msg.subject == "Test Subject"

    @patch('mailclean.imap_client.imaplib.IMAP4_SSL')
    def test_fetch_email_with_body(self, mock_imap_class):
        """Test fetching email with body content."""
        raw_email = self.create_raw_email(body="This is the email body.")

        mock_imap = Mock()
        mock_imap.select.return_value = ('OK', [b'100'])
        mock_imap.uid.return_value = ('OK', [(b'1 (UID 1 RFC822 {100}', raw_email), b')'])
        mock_imap_class.return_value = mock_imap

        client = IMAPClient("imap.example.com", 993, "user@example.com", "password")
        client.connect()
        client.select_folder("INBOX")
        email_msg = client.fetch_email(1, include_body=True)

        assert email_msg is not None
        assert "This is the email body" in email_msg.body
