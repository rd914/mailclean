"""IMAP client for email operations."""

import email
import email.header
import email.utils
import imaplib
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, Iterator, Optional

from .models import EmailMessage

MAILCLEAN_DELETED_FOLDER = 'MailClean-Deleted'
MAILCLEAN_HEADER = 'X-MailClean-Original-Folder'
MAILCLEAN_DELETED_DATE_HEADER = 'X-MailClean-Deleted-Date'


class IMAPError(Exception):
    """Error during IMAP operations."""
    pass


class IMAPClient:
    """IMAP client for email operations."""

    def __init__(self, server: str, port: int, email_addr: str, password: str, use_ssl: bool = True):
        self.server = server
        self.port = port
        self.email_addr = email_addr
        self.password = password
        self.use_ssl = use_ssl
        self._connection: Optional[imaplib.IMAP4_SSL | imaplib.IMAP4] = None
        self._current_folder: Optional[str] = None

    def connect(self) -> None:
        """Establish connection to the IMAP server."""
        try:
            if self.use_ssl:
                self._connection = imaplib.IMAP4_SSL(self.server, self.port)
            else:
                self._connection = imaplib.IMAP4(self.server, self.port)

            self._connection.login(self.email_addr, self.password)
        except imaplib.IMAP4.error as e:
            raise IMAPError(f"Failed to connect: {e}") from e

    def disconnect(self) -> None:
        """Close the IMAP connection."""
        if self._connection:
            try:
                self._connection.logout()
            except Exception:
                pass
            self._connection = None
            self._current_folder = None

    @contextmanager
    def connection(self) -> Generator['IMAPClient', None, None]:
        """Context manager for IMAP connection."""
        self.connect()
        try:
            yield self
        finally:
            self.disconnect()

    def _check_connection(self) -> None:
        if not self._connection:
            raise IMAPError("Not connected to server")

    def list_folders(self) -> list[str]:
        """List all folders on the server."""
        self._check_connection()

        status, data = self._connection.list()
        if status != 'OK':
            raise IMAPError("Failed to list folders")

        folders = []
        for item in data:
            if item is None:
                continue
            # Parse folder name from IMAP response
            # Format: (\\flags) "/" "folder name"
            match = re.search(rb'"([^"]*)"$|([^ ]+)$', item)
            if match:
                folder_name = match.group(1) or match.group(2)
                if folder_name:
                    # Decode IMAP modified UTF-7 encoding
                    decoded = self._decode_imap_utf7(folder_name)
                    folders.append(decoded)

        return folders

    def _decode_imap_utf7(self, data: bytes) -> str:
        """Decode IMAP modified UTF-7 folder name."""
        # IMAP uses a modified UTF-7 encoding for folder names
        # This is a simplified decoder that handles common cases
        try:
            # First try simple ASCII decode
            text = data.decode('ascii')
            # Convert IMAP UTF-7 sequences (&...-)
            result = []
            i = 0
            while i < len(text):
                if text[i] == '&':
                    if i + 1 < len(text) and text[i + 1] == '-':
                        # &- represents a literal &
                        result.append('&')
                        i += 2
                    else:
                        # Find the closing -
                        end = text.find('-', i + 1)
                        if end == -1:
                            result.append(text[i:])
                            break
                        # Decode the UTF-7 portion
                        encoded = text[i + 1:end]
                        # Convert from modified base64 to standard base64
                        encoded = encoded.replace(',', '/')
                        try:
                            import base64
                            decoded_bytes = base64.b64decode(encoded + '==')
                            result.append(decoded_bytes.decode('utf-16-be'))
                        except Exception:
                            result.append(text[i:end + 1])
                        i = end + 1
                else:
                    result.append(text[i])
                    i += 1
            return ''.join(result)
        except UnicodeDecodeError:
            return data.decode('utf-8', errors='replace')

    def select_folder(self, folder: str) -> int:
        """Select a folder and return the message count."""
        self._check_connection()

        # Encode folder name for IMAP
        encoded_folder = folder

        status, data = self._connection.select(encoded_folder)
        if status != 'OK':
            raise IMAPError(f"Failed to select folder: {folder}")

        self._current_folder = folder
        return int(data[0])

    def create_folder(self, folder: str) -> None:
        """Create a folder if it doesn't exist."""
        self._check_connection()

        status, _ = self._connection.create(folder)
        # Ignore error if folder already exists
        if status != 'OK':
            # Check if folder exists
            folders = self.list_folders()
            if folder not in folders:
                raise IMAPError(f"Failed to create folder: {folder}")

    def ensure_mailclean_folder(self) -> None:
        """Ensure the MailClean-Deleted folder exists."""
        folders = self.list_folders()
        if MAILCLEAN_DELETED_FOLDER not in folders:
            self.create_folder(MAILCLEAN_DELETED_FOLDER)

    def search(self, criteria: str = 'ALL') -> list[int]:
        """Search for messages matching IMAP criteria."""
        self._check_connection()

        if not self._current_folder:
            raise IMAPError("No folder selected")

        status, data = self._connection.search(None, criteria)
        if status != 'OK':
            raise IMAPError("Search failed")

        if not data[0]:
            return []

        return [int(uid) for uid in data[0].split()]

    def search_uids(self, criteria: str = 'ALL') -> list[int]:
        """Search for messages and return UIDs."""
        self._check_connection()

        if not self._current_folder:
            raise IMAPError("No folder selected")

        status, data = self._connection.uid('search', None, criteria)
        if status != 'OK':
            raise IMAPError("Search failed")

        if not data[0]:
            return []

        return [int(uid) for uid in data[0].split()]

    def fetch_email(self, uid: int, include_body: bool = False) -> Optional[EmailMessage]:
        """Fetch an email by UID."""
        self._check_connection()

        if not self._current_folder:
            raise IMAPError("No folder selected")

        fetch_parts = '(RFC822.HEADER)'
        if include_body:
            fetch_parts = '(RFC822)'

        status, data = self._connection.uid('fetch', str(uid), fetch_parts)
        if status != 'OK' or not data or data[0] is None:
            return None

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        return self._parse_email(msg, uid, include_body)

    def fetch_emails(
        self,
        uids: list[int],
        include_body: bool = False,
        batch_size: int = 50
    ) -> Iterator[EmailMessage]:
        """Fetch multiple emails by UID in batches."""
        self._check_connection()

        if not self._current_folder:
            raise IMAPError("No folder selected")

        for i in range(0, len(uids), batch_size):
            batch = uids[i:i + batch_size]
            uid_str = ','.join(str(uid) for uid in batch)

            fetch_parts = '(RFC822.HEADER)'
            if include_body:
                fetch_parts = '(RFC822)'

            status, data = self._connection.uid('fetch', uid_str, fetch_parts)
            if status != 'OK':
                continue

            for item in data:
                if item is None or not isinstance(item, tuple):
                    continue

                # Extract UID from response
                uid_match = re.search(rb'UID (\d+)', item[0])
                if not uid_match:
                    continue

                uid = int(uid_match.group(1))
                raw_email = item[1]
                msg = email.message_from_bytes(raw_email)
                parsed = self._parse_email(msg, uid, include_body)
                if parsed:
                    yield parsed

    def _parse_email(self, msg: email.message.Message, uid: int, include_body: bool) -> EmailMessage:
        """Parse an email.message.Message into an EmailMessage."""
        # Decode subject
        subject = self._decode_header(msg.get('Subject', ''))

        # Parse from address
        from_addr = self._parse_address(msg.get('From', ''))

        # Parse recipient addresses
        to_addrs = self._parse_address_list(msg.get('To', ''))
        cc_addrs = self._parse_address_list(msg.get('Cc', ''))
        bcc_addrs = self._parse_address_list(msg.get('Bcc', ''))

        # Parse date
        date_str = msg.get('Date', '')
        date = None
        if date_str:
            try:
                parsed = email.utils.parsedate_to_datetime(date_str)
                date = parsed
            except (ValueError, TypeError):
                pass

        # Get message ID
        message_id = msg.get('Message-ID', f'<{uid}@local>')

        # Get body if requested
        body = None
        if include_body:
            body = self._get_body(msg)

        # Get MailClean headers if present
        original_folder = msg.get(MAILCLEAN_HEADER)
        deleted_date_str = msg.get(MAILCLEAN_DELETED_DATE_HEADER)
        deleted_date = None
        if deleted_date_str:
            try:
                deleted_date = datetime.fromisoformat(deleted_date_str)
            except ValueError:
                pass

        # Collect all headers
        headers = {k: self._decode_header(v) for k, v in msg.items()}

        return EmailMessage(
            message_id=message_id,
            uid=uid,
            subject=subject,
            from_address=from_addr,
            to_addresses=to_addrs,
            cc_addresses=cc_addrs,
            bcc_addresses=bcc_addrs,
            date=date,
            folder=self._current_folder or '',
            body=body,
            headers=headers,
            original_folder=original_folder,
            deleted_date=deleted_date,
        )

    def _decode_header(self, header: str) -> str:
        """Decode a MIME-encoded header."""
        if not header:
            return ''

        decoded_parts = []
        for part, charset in email.header.decode_header(header):
            if isinstance(part, bytes):
                charset = charset or 'utf-8'
                try:
                    decoded_parts.append(part.decode(charset, errors='replace'))
                except LookupError:
                    decoded_parts.append(part.decode('utf-8', errors='replace'))
            else:
                decoded_parts.append(part)

        return ''.join(decoded_parts)

    def _parse_address(self, addr_str: str) -> str:
        """Parse a single email address."""
        if not addr_str:
            return ''

        # Decode if MIME-encoded
        decoded = self._decode_header(addr_str)

        # Extract just the email address
        name, addr = email.utils.parseaddr(decoded)
        return addr if addr else decoded

    def _parse_address_list(self, addr_str: str) -> list[str]:
        """Parse a comma-separated list of email addresses."""
        if not addr_str:
            return []

        decoded = self._decode_header(addr_str)
        addresses = []

        for name, addr in email.utils.getaddresses([decoded]):
            if addr:
                addresses.append(addr)

        return addresses

    def _get_body(self, msg: email.message.Message) -> str:
        """Extract the body text from an email message."""
        body_parts = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition', ''))

                # Skip attachments
                if 'attachment' in content_disposition:
                    continue

                if content_type == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        try:
                            body_parts.append(payload.decode(charset, errors='replace'))
                        except LookupError:
                            body_parts.append(payload.decode('utf-8', errors='replace'))
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                try:
                    body_parts.append(payload.decode(charset, errors='replace'))
                except (LookupError, AttributeError):
                    if isinstance(payload, bytes):
                        body_parts.append(payload.decode('utf-8', errors='replace'))
                    else:
                        body_parts.append(str(payload))

        return '\n'.join(body_parts)

    def move_to_mailclean_deleted(self, uids: list[int], source_folder: str) -> int:
        """Move messages to MailClean-Deleted folder."""
        self._check_connection()
        self.ensure_mailclean_folder()

        # Select source folder
        self.select_folder(source_folder)

        moved_count = 0
        for uid in uids:
            try:
                # Copy to MailClean-Deleted
                status, _ = self._connection.uid('copy', str(uid), MAILCLEAN_DELETED_FOLDER)
                if status == 'OK':
                    # Mark original as deleted
                    self._connection.uid('store', str(uid), '+FLAGS', '\\Deleted')
                    moved_count += 1
            except Exception:
                continue

        # Expunge deleted messages
        self._connection.expunge()

        return moved_count

    def restore_from_mailclean_deleted(self, uids: list[int], target_folder: str = 'INBOX') -> int:
        """Restore messages from MailClean-Deleted to target folder."""
        self._check_connection()

        # Select MailClean-Deleted folder
        self.select_folder(MAILCLEAN_DELETED_FOLDER)

        restored_count = 0
        for uid in uids:
            try:
                # Get original folder from email if available
                email_msg = self.fetch_email(uid, include_body=False)
                dest_folder = target_folder
                if email_msg and email_msg.original_folder:
                    dest_folder = email_msg.original_folder

                # Copy to destination
                status, _ = self._connection.uid('copy', str(uid), dest_folder)
                if status == 'OK':
                    # Mark as deleted in MailClean-Deleted
                    self._connection.uid('store', str(uid), '+FLAGS', '\\Deleted')
                    restored_count += 1
            except Exception:
                continue

        # Expunge deleted messages
        self._connection.expunge()

        return restored_count

    def permanently_delete(self, uids: list[int]) -> int:
        """Permanently delete messages (for purge operation)."""
        self._check_connection()

        if not self._current_folder:
            raise IMAPError("No folder selected")

        deleted_count = 0
        for uid in uids:
            try:
                status, _ = self._connection.uid('store', str(uid), '+FLAGS', '\\Deleted')
                if status == 'OK':
                    deleted_count += 1
            except Exception:
                continue

        self._connection.expunge()

        return deleted_count

    def get_emails_older_than(self, days: int) -> list[int]:
        """Get UIDs of emails older than specified days in current folder."""
        self._check_connection()

        if not self._current_folder:
            raise IMAPError("No folder selected")

        # Calculate the date
        cutoff = datetime.now() - __import__('datetime').timedelta(days=days)
        date_str = cutoff.strftime('%d-%b-%Y')

        return self.search_uids(f'BEFORE {date_str}')
