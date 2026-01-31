"""Data models for email messages."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Optional

from .utils import scrub_text


@dataclass
class EmailMessage:
    """Represents an email message."""

    message_id: str
    uid: int
    subject: str
    from_address: str
    to_addresses: list[str]
    cc_addresses: list[str]
    bcc_addresses: list[str]
    date: Optional[datetime]
    folder: str
    body: Optional[str] = None
    headers: dict[str, str] = field(default_factory=dict)

    # Metadata for deleted emails
    original_folder: Optional[str] = None
    deleted_date: Optional[datetime] = None

    @property
    def all_recipients(self) -> list[str]:
        """Get all recipient addresses (To, CC, BCC)."""
        return self.to_addresses + self.cc_addresses + self.bcc_addresses

    def to_dict(self) -> dict:
        """Convert to dictionary for export."""
        return {
            'message_id': self.message_id,
            'uid': self.uid,
            'subject': self.subject,
            'from': self.from_address,
            'to': ', '.join(self.to_addresses),
            'cc': ', '.join(self.cc_addresses),
            'bcc': ', '.join(self.bcc_addresses),
            'date': self.date.isoformat() if self.date else None,
            'folder': self.folder,
            'headers': self.headers,
        }

    def to_csv_row(self) -> dict:
        """Convert to flat dictionary for CSV export."""
        return {
            'message_id': self.message_id,
            'date': self.date.isoformat() if self.date else '',
            'from': self.from_address,
            'to': ', '.join(self.to_addresses),
            'subject': self.subject,
            'folder': self.folder,
        }

    def scrubbed(self) -> 'EmailMessage':
        """
        Return a copy with text fields scrubbed for spam detection.

        Applies normalization to counter spam obfuscation techniques:
        - Unicode homoglyph substitution (é→e, ö→o, etc.)
        - Backspace character tricks
        """
        return replace(
            self,
            subject=scrub_text(self.subject),
            from_address=scrub_text(self.from_address),
            to_addresses=[scrub_text(addr) for addr in self.to_addresses],
            cc_addresses=[scrub_text(addr) for addr in self.cc_addresses],
            bcc_addresses=[scrub_text(addr) for addr in self.bcc_addresses],
            body=scrub_text(self.body) if self.body else None,
        )
