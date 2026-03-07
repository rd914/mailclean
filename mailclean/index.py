"""Local email index for fast header-based filtering without repeated IMAP fetches."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional

from .models import EmailMessage

INDEX_DIR = Path.home() / '.mailclean' / 'index'
DEFAULT_MAX_AGE_DAYS = 7


def _folder_to_filename(folder: str) -> str:
    safe = folder.replace('/', '_').replace('\\', '_')
    return f"{safe}.json"


def _serialize(email_msg: EmailMessage) -> dict:
    return {
        'uid': email_msg.uid,
        'message_id': email_msg.message_id,
        'subject': email_msg.subject,
        'from_address': email_msg.from_address,
        'to_addresses': email_msg.to_addresses,
        'cc_addresses': email_msg.cc_addresses,
        'bcc_addresses': email_msg.bcc_addresses,
        'date': email_msg.date.isoformat() if email_msg.date else None,
        'folder': email_msg.folder,
    }


def _deserialize(data: dict) -> EmailMessage:
    date = None
    if data.get('date'):
        try:
            date = datetime.fromisoformat(data['date'])
        except (ValueError, TypeError):
            pass
    return EmailMessage(
        uid=data['uid'],
        message_id=data.get('message_id', ''),
        subject=data.get('subject', ''),
        from_address=data.get('from_address', ''),
        to_addresses=data.get('to_addresses', []),
        cc_addresses=data.get('cc_addresses', []),
        bcc_addresses=data.get('bcc_addresses', []),
        date=date,
        folder=data.get('folder', ''),
    )


class MailIndex:
    """
    Local cache of email headers for a single account/folder.

    Workflow:
      1. load() — read from disk if it exists
      2. needs_full_rebuild() — check if scheduled rebuild is due
      3. full_rebuild(client) or sync(client) — update from IMAP
      4. iter_emails() — filter locally without additional IMAP traffic
      5. invalidate_uids() — call after delete/restore to keep index accurate
    """

    def __init__(self, account_name: str, folder: str):
        self.account_name = account_name
        self.folder = folder
        self._path = INDEX_DIR / account_name / _folder_to_filename(folder)
        self._emails: dict[int, dict] = {}
        self._built_at: Optional[datetime] = None
        self._last_synced_at: Optional[datetime] = None
        self._full_rebuild_at: Optional[datetime] = None

    # ── properties ──────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    @property
    def exists(self) -> bool:
        return self._path.exists()

    @property
    def email_count(self) -> int:
        return len(self._emails)

    @property
    def built_at(self) -> Optional[datetime]:
        return self._built_at

    @property
    def last_synced_at(self) -> Optional[datetime]:
        return self._last_synced_at

    @property
    def full_rebuild_at(self) -> Optional[datetime]:
        return self._full_rebuild_at

    # ── disk I/O ─────────────────────────────────────────────────────────────

    def load(self) -> bool:
        """Load index from disk. Returns True if loaded successfully."""
        if not self._path.exists():
            return False
        try:
            with open(self._path) as f:
                data = json.load(f)
            self._emails = {int(k): v for k, v in data.get('emails', {}).items()}
            for attr, key in [
                ('_built_at', 'built_at'),
                ('_last_synced_at', 'last_synced_at'),
                ('_full_rebuild_at', 'full_rebuild_at'),
            ]:
                raw = data.get(key)
                if raw:
                    setattr(self, attr, datetime.fromisoformat(raw))
            return True
        except (json.JSONDecodeError, KeyError, ValueError):
            return False

    def save(self) -> None:
        """Persist index to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'account': self.account_name,
            'folder': self.folder,
            'built_at': self._built_at.isoformat() if self._built_at else None,
            'last_synced_at': self._last_synced_at.isoformat() if self._last_synced_at else None,
            'full_rebuild_at': self._full_rebuild_at.isoformat() if self._full_rebuild_at else None,
            'emails': {str(uid): d for uid, d in self._emails.items()},
        }
        with open(self._path, 'w') as f:
            json.dump(data, f)

    # ── rebuild logic ────────────────────────────────────────────────────────

    def needs_full_rebuild(self, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> bool:
        """Return True if the index has never been fully built or is past max_age_days."""
        if not self._full_rebuild_at:
            return True
        age = datetime.now(timezone.utc) - self._full_rebuild_at
        return age.days >= max_age_days

    def full_rebuild(
        self,
        client,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        Discard cached data and re-fetch all email headers from the server.
        Returns the number of emails indexed.
        """
        self._emails = {}
        uids = client.search_uids('ALL')

        if on_progress:
            on_progress(f"Building index ({len(uids)} emails)...")

        for email_msg in client.fetch_emails(uids, include_body=False):
            self._emails[email_msg.uid] = _serialize(email_msg)

        now = datetime.now(timezone.utc)
        self._built_at = self._built_at or now
        self._last_synced_at = now
        self._full_rebuild_at = now
        self.save()
        return len(self._emails)

    def sync(
        self,
        client,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> tuple[int, int]:
        """
        Incrementally sync: remove UIDs no longer on the server, fetch new ones.
        Returns (added, removed) counts.
        """
        server_uids = set(client.search_uids('ALL'))
        index_uids = set(self._emails.keys())

        removed = index_uids - server_uids
        new_uids = list(server_uids - index_uids)

        for uid in removed:
            del self._emails[uid]

        if new_uids:
            if on_progress:
                on_progress(f"Fetching {len(new_uids)} new emails for index...")
            for email_msg in client.fetch_emails(new_uids, include_body=False):
                self._emails[email_msg.uid] = _serialize(email_msg)

        now = datetime.now(timezone.utc)
        self._built_at = self._built_at or now
        self._last_synced_at = now
        self.save()
        return len(new_uids), len(removed)

    # ── querying ─────────────────────────────────────────────────────────────

    def iter_emails(self) -> Iterator[EmailMessage]:
        """Yield all indexed EmailMessage objects."""
        for data in self._emails.values():
            yield _deserialize(data)

    def get_uids(self) -> list[int]:
        return list(self._emails.keys())

    # ── post-mutation ────────────────────────────────────────────────────────

    def invalidate_uids(self, uids: list[int]) -> None:
        """
        Remove specific UIDs from the index after a delete or restore.
        Keeps the index accurate without a full sync.
        """
        for uid in uids:
            self._emails.pop(uid, None)
        self._last_synced_at = datetime.now(timezone.utc)
        self.save()


def load_and_sync(
    account_name: str,
    folder: str,
    client,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    on_progress: Optional[Callable[[str], None]] = None,
) -> 'MailIndex':
    """
    Load the index for an account/folder and bring it up to date.

    Performs a full rebuild when:
      - No index file exists yet
      - The last full rebuild is older than max_age_days

    Otherwise performs a fast incremental sync (only new/removed UIDs).
    """
    index = MailIndex(account_name, folder)
    loaded = index.load()

    if not loaded or index.needs_full_rebuild(max_age_days):
        if on_progress:
            on_progress("Building email index...")
        index.full_rebuild(client, on_progress=on_progress)
    else:
        if on_progress:
            on_progress("Syncing index...")
        index.sync(client, on_progress=on_progress)

    return index
