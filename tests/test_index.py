"""Tests for the email index."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mailclean.index import (
    MailIndex,
    _folder_to_filename,
    _serialize,
    _deserialize,
    load_and_sync,
    DEFAULT_MAX_AGE_DAYS,
)
from mailclean.models import EmailMessage


def make_email(uid: int = 1, folder: str = 'INBOX', **kwargs) -> EmailMessage:
    defaults = dict(
        message_id=f'<{uid}@test>',
        uid=uid,
        subject='Test Subject',
        from_address='sender@example.com',
        to_addresses=['recipient@example.com'],
        cc_addresses=[],
        bcc_addresses=[],
        date=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        folder=folder,
    )
    defaults.update(kwargs)
    return EmailMessage(**defaults)


def make_client(uids: list[int], emails: list[EmailMessage]) -> MagicMock:
    client = MagicMock()
    client.search_uids.return_value = uids
    client.fetch_emails.return_value = iter(emails)
    return client


# ── helpers ──────────────────────────────────────────────────────────────────

class TestFolderToFilename:
    def test_simple(self):
        assert _folder_to_filename('INBOX') == 'INBOX.json'

    def test_slash_replaced(self):
        assert _folder_to_filename('Folder/Sub') == 'Folder_Sub.json'

    def test_backslash_replaced(self):
        assert _folder_to_filename('Folder\\Sub') == 'Folder_Sub.json'


class TestSerializeDeserialize:
    def test_roundtrip(self):
        email = make_email(uid=42)
        data = _serialize(email)
        restored = _deserialize(data)

        assert restored.uid == 42
        assert restored.subject == email.subject
        assert restored.from_address == email.from_address
        assert restored.to_addresses == email.to_addresses
        assert restored.date == email.date

    def test_none_date(self):
        email = make_email(date=None)
        data = _serialize(email)
        assert data['date'] is None
        restored = _deserialize(data)
        assert restored.date is None


# ── MailIndex ─────────────────────────────────────────────────────────────────

class TestMailIndex:
    def test_empty_index(self, tmp_path):
        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            assert not index.exists
            assert index.email_count == 0

    def test_full_rebuild(self, tmp_path):
        emails = [make_email(uid=i) for i in [1, 2, 3]]
        client = make_client([1, 2, 3], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            count = index.full_rebuild(client)

        assert count == 3
        assert index.email_count == 3
        assert index.full_rebuild_at is not None
        assert index.last_synced_at is not None

    def test_full_rebuild_saves_to_disk(self, tmp_path):
        emails = [make_email(uid=1)]
        client = make_client([1], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)
            assert index.path.exists()

    def test_load_after_rebuild(self, tmp_path):
        emails = [make_email(uid=i) for i in [1, 2]]
        client = make_client([1, 2], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)

            index2 = MailIndex('account', 'INBOX')
            loaded = index2.load()

        assert loaded
        assert index2.email_count == 2

    def test_sync_adds_new_uids(self, tmp_path):
        initial_emails = [make_email(uid=1), make_email(uid=2)]
        client = make_client([1, 2], initial_emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)

            # New email arrives
            new_email = make_email(uid=3)
            client.search_uids.return_value = [1, 2, 3]
            client.fetch_emails.return_value = iter([new_email])

            added, removed = index.sync(client)

        assert added == 1
        assert removed == 0
        assert index.email_count == 3

    def test_sync_removes_deleted_uids(self, tmp_path):
        initial_emails = [make_email(uid=1), make_email(uid=2), make_email(uid=3)]
        client = make_client([1, 2, 3], initial_emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)

            # uid 2 deleted on server
            client.search_uids.return_value = [1, 3]
            client.fetch_emails.return_value = iter([])

            added, removed = index.sync(client)

        assert added == 0
        assert removed == 1
        assert index.email_count == 2

    def test_needs_full_rebuild_no_history(self, tmp_path):
        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            assert index.needs_full_rebuild()

    def test_needs_full_rebuild_fresh(self, tmp_path):
        emails = [make_email(uid=1)]
        client = make_client([1], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)
            assert not index.needs_full_rebuild()

    def test_needs_full_rebuild_old(self, tmp_path):
        emails = [make_email(uid=1)]
        client = make_client([1], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)
            # Simulate old rebuild timestamp
            old_time = datetime.now(timezone.utc) - timedelta(days=DEFAULT_MAX_AGE_DAYS + 1)
            index._full_rebuild_at = old_time
            assert index.needs_full_rebuild()

    def test_iter_emails(self, tmp_path):
        emails = [make_email(uid=i, subject=f'Email {i}') for i in [1, 2, 3]]
        client = make_client([1, 2, 3], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)

            result = list(index.iter_emails())

        assert len(result) == 3
        subjects = {e.subject for e in result}
        assert subjects == {'Email 1', 'Email 2', 'Email 3'}

    def test_get_uids(self, tmp_path):
        emails = [make_email(uid=i) for i in [10, 20, 30]]
        client = make_client([10, 20, 30], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)
            uids = set(index.get_uids())

        assert uids == {10, 20, 30}

    def test_invalidate_uids(self, tmp_path):
        emails = [make_email(uid=i) for i in [1, 2, 3]]
        client = make_client([1, 2, 3], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)
            index.invalidate_uids([1, 3])

        assert index.email_count == 1
        assert list(index.get_uids()) == [2]

    def test_invalidate_uids_persists(self, tmp_path):
        emails = [make_email(uid=i) for i in [1, 2, 3]]
        client = make_client([1, 2, 3], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client)
            index.invalidate_uids([2])

            index2 = MailIndex('account', 'INBOX')
            index2.load()

        assert index2.email_count == 2
        assert 2 not in index2.get_uids()

    def test_load_corrupt_file_returns_false(self, tmp_path):
        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.path.parent.mkdir(parents=True, exist_ok=True)
            index.path.write_text('not valid json')

            result = index.load()

        assert result is False

    def test_progress_callback_called(self, tmp_path):
        emails = [make_email(uid=1)]
        client = make_client([1], emails)
        messages = []

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = MailIndex('account', 'INBOX')
            index.full_rebuild(client, on_progress=messages.append)

        assert len(messages) > 0


class TestLoadAndSync:
    def test_builds_when_no_index(self, tmp_path):
        emails = [make_email(uid=i) for i in [1, 2]]
        client = make_client([1, 2], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = load_and_sync('account', 'INBOX', client)

        assert index.email_count == 2
        assert index.full_rebuild_at is not None

    def test_syncs_when_index_exists_and_fresh(self, tmp_path):
        emails = [make_email(uid=1)]
        client = make_client([1], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            # First call: builds
            load_and_sync('account', 'INBOX', client)

            # Second call: incremental sync only
            new_email = make_email(uid=2)
            client.search_uids.return_value = [1, 2]
            client.fetch_emails.return_value = iter([new_email])

            index2 = load_and_sync('account', 'INBOX', client)

        assert index2.email_count == 2
        # fetch_emails called twice total (once for build, once for sync new uid)
        assert client.fetch_emails.call_count == 2

    def test_rebuilds_when_old(self, tmp_path):
        emails = [make_email(uid=1)]
        client = make_client([1], emails)

        with patch('mailclean.index.INDEX_DIR', tmp_path):
            index = load_and_sync('account', 'INBOX', client)
            # Backdate the full_rebuild_at
            old_time = datetime.now(timezone.utc) - timedelta(days=DEFAULT_MAX_AGE_DAYS + 1)
            index._full_rebuild_at = old_time
            index.save()

            client.fetch_emails.return_value = iter(emails)
            index2 = load_and_sync('account', 'INBOX', client)

        # full_rebuild_at should be updated to now
        assert index2.full_rebuild_at > old_time
