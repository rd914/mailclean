"""Tests for the query criteria."""

import pytest
from datetime import datetime, timedelta

from mailclean.models import EmailMessage
from mailclean.query.criteria import (
    FromCriterion, ToCriterion, CcCriterion, BccCriterion, AddresseeCriterion,
    DateCriterion, BeforeCriterion, AfterCriterion,
    OlderThanCriterion, NewerThanCriterion,
    SubjectCriterion, BodyCriterion,
    AndCriterion, OrCriterion, NotCriterion,
)


def make_email(
    from_address: str = "sender@example.com",
    to_addresses: list[str] = None,
    cc_addresses: list[str] = None,
    bcc_addresses: list[str] = None,
    subject: str = "Test Subject",
    body: str = "Test body content",
    date: datetime = None,
) -> EmailMessage:
    """Create a test email message."""
    return EmailMessage(
        message_id="<test@example.com>",
        uid=1,
        subject=subject,
        from_address=from_address,
        to_addresses=to_addresses or ["recipient@example.com"],
        cc_addresses=cc_addresses or [],
        bcc_addresses=bcc_addresses or [],
        date=date or datetime.now(),
        folder="INBOX",
        body=body,
    )


class TestFromCriterion:
    """Tests for FromCriterion."""

    def test_exact_match(self):
        """Test exact email match."""
        criterion = FromCriterion("sender@example.com")
        email = make_email(from_address="sender@example.com")

        assert criterion.matches(email)

    def test_no_match(self):
        """Test non-matching email."""
        criterion = FromCriterion("other@example.com")
        email = make_email(from_address="sender@example.com")

        assert not criterion.matches(email)

    def test_wildcard_domain(self):
        """Test wildcard domain match."""
        criterion = FromCriterion("*@example.com")
        email = make_email(from_address="anyone@example.com")

        assert criterion.matches(email)

    def test_wildcard_user(self):
        """Test wildcard user match."""
        criterion = FromCriterion("admin@*")
        email = make_email(from_address="admin@company.com")

        assert criterion.matches(email)

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        criterion = FromCriterion("SENDER@EXAMPLE.COM")
        email = make_email(from_address="sender@example.com")

        assert criterion.matches(email)


class TestToCriterion:
    """Tests for ToCriterion."""

    def test_match(self):
        """Test To address match."""
        criterion = ToCriterion("recipient@example.com")
        email = make_email(to_addresses=["recipient@example.com"])

        assert criterion.matches(email)

    def test_multiple_recipients(self):
        """Test matching one of multiple recipients."""
        criterion = ToCriterion("bob@example.com")
        email = make_email(to_addresses=["alice@example.com", "bob@example.com"])

        assert criterion.matches(email)


class TestCcCriterion:
    """Tests for CcCriterion."""

    def test_match(self):
        """Test CC address match."""
        criterion = CcCriterion("cc@example.com")
        email = make_email(cc_addresses=["cc@example.com"])

        assert criterion.matches(email)

    def test_no_cc(self):
        """Test no match when CC is empty."""
        criterion = CcCriterion("cc@example.com")
        email = make_email(cc_addresses=[])

        assert not criterion.matches(email)


class TestBccCriterion:
    """Tests for BccCriterion."""

    def test_match(self):
        """Test BCC address match."""
        criterion = BccCriterion("bcc@example.com")
        email = make_email(bcc_addresses=["bcc@example.com"])

        assert criterion.matches(email)


class TestAddresseeCriterion:
    """Tests for AddresseeCriterion."""

    def test_match_to(self):
        """Test matching To address."""
        criterion = AddresseeCriterion("recipient@example.com")
        email = make_email(to_addresses=["recipient@example.com"])

        assert criterion.matches(email)

    def test_match_cc(self):
        """Test matching CC address."""
        criterion = AddresseeCriterion("cc@example.com")
        email = make_email(to_addresses=[], cc_addresses=["cc@example.com"])

        assert criterion.matches(email)

    def test_match_bcc(self):
        """Test matching BCC address."""
        criterion = AddresseeCriterion("bcc@example.com")
        email = make_email(to_addresses=[], bcc_addresses=["bcc@example.com"])

        assert criterion.matches(email)


class TestDateCriterion:
    """Tests for DateCriterion."""

    def test_exact_date_match(self):
        """Test exact date match."""
        criterion = DateCriterion("2024-06-15")
        email = make_email(date=datetime(2024, 6, 15, 10, 30))

        assert criterion.matches(email)

    def test_different_date(self):
        """Test different date doesn't match."""
        criterion = DateCriterion("2024-06-15")
        email = make_email(date=datetime(2024, 6, 16, 10, 30))

        assert not criterion.matches(email)

    def test_invalid_date_raises(self):
        """Test invalid date raises error."""
        with pytest.raises(ValueError):
            DateCriterion("not-a-date")


class TestBeforeCriterion:
    """Tests for BeforeCriterion."""

    def test_before_match(self):
        """Test email before date matches."""
        criterion = BeforeCriterion("2024-06-15")
        email = make_email(date=datetime(2024, 6, 1))

        assert criterion.matches(email)

    def test_after_no_match(self):
        """Test email after date doesn't match."""
        criterion = BeforeCriterion("2024-06-15")
        email = make_email(date=datetime(2024, 6, 20))

        assert not criterion.matches(email)


class TestAfterCriterion:
    """Tests for AfterCriterion."""

    def test_after_match(self):
        """Test email after date matches."""
        criterion = AfterCriterion("2024-06-15")
        email = make_email(date=datetime(2024, 6, 20))

        assert criterion.matches(email)

    def test_before_no_match(self):
        """Test email before date doesn't match."""
        criterion = AfterCriterion("2024-06-15")
        email = make_email(date=datetime(2024, 6, 1))

        assert not criterion.matches(email)


class TestOlderThanCriterion:
    """Tests for OlderThanCriterion."""

    def test_older_than_days(self):
        """Test older than N days."""
        criterion = OlderThanCriterion("30d")
        email = make_email(date=datetime.now() - timedelta(days=45))

        assert criterion.matches(email)

    def test_not_older_than_days(self):
        """Test not older than N days."""
        criterion = OlderThanCriterion("30d")
        email = make_email(date=datetime.now() - timedelta(days=15))

        assert not criterion.matches(email)

    def test_older_than_weeks(self):
        """Test older than N weeks."""
        criterion = OlderThanCriterion("2w")
        email = make_email(date=datetime.now() - timedelta(weeks=3))

        assert criterion.matches(email)

    def test_older_than_months(self):
        """Test older than N months."""
        criterion = OlderThanCriterion("3m")
        email = make_email(date=datetime.now() - timedelta(days=100))

        assert criterion.matches(email)

    def test_invalid_format(self):
        """Test invalid relative date format."""
        with pytest.raises(ValueError):
            OlderThanCriterion("invalid")


class TestNewerThanCriterion:
    """Tests for NewerThanCriterion."""

    def test_newer_than_days(self):
        """Test newer than N days."""
        criterion = NewerThanCriterion("30d")
        email = make_email(date=datetime.now() - timedelta(days=15))

        assert criterion.matches(email)

    def test_not_newer_than_days(self):
        """Test not newer than N days."""
        criterion = NewerThanCriterion("30d")
        email = make_email(date=datetime.now() - timedelta(days=45))

        assert not criterion.matches(email)


class TestSubjectCriterion:
    """Tests for SubjectCriterion."""

    def test_simple_match(self):
        """Test simple subject match."""
        criterion = SubjectCriterion("/newsletter/i")
        email = make_email(subject="Weekly Newsletter Update")

        assert criterion.matches(email)

    def test_case_insensitive(self):
        """Test case insensitive match."""
        criterion = SubjectCriterion("/NEWSLETTER/i")
        email = make_email(subject="Weekly newsletter Update")

        assert criterion.matches(email)

    def test_no_match(self):
        """Test non-matching subject."""
        criterion = SubjectCriterion("/newsletter/")
        email = make_email(subject="Important Meeting")

        assert not criterion.matches(email)

    def test_regex_pattern(self):
        """Test regex pattern matching."""
        criterion = SubjectCriterion("/^Re:/")
        email = make_email(subject="Re: Your message")

        assert criterion.matches(email)


class TestBodyCriterion:
    """Tests for BodyCriterion."""

    def test_match(self):
        """Test body content match."""
        criterion = BodyCriterion("/unsubscribe/i")
        email = make_email(body="Click here to Unsubscribe from this list.")

        assert criterion.matches(email)

    def test_no_body(self):
        """Test no match when body is None."""
        criterion = BodyCriterion("/test/")
        email = make_email(body=None)

        assert not criterion.matches(email)


class TestAndCriterion:
    """Tests for AndCriterion."""

    def test_both_match(self):
        """Test both criteria match."""
        criterion = AndCriterion(
            FromCriterion("sender@example.com"),
            SubjectCriterion("/test/i"),
        )
        email = make_email(from_address="sender@example.com", subject="Test email")

        assert criterion.matches(email)

    def test_left_only_match(self):
        """Test only left criterion matches."""
        criterion = AndCriterion(
            FromCriterion("sender@example.com"),
            SubjectCriterion("/newsletter/"),
        )
        email = make_email(from_address="sender@example.com", subject="Test email")

        assert not criterion.matches(email)

    def test_right_only_match(self):
        """Test only right criterion matches."""
        criterion = AndCriterion(
            FromCriterion("other@example.com"),
            SubjectCriterion("/test/i"),
        )
        email = make_email(from_address="sender@example.com", subject="Test email")

        assert not criterion.matches(email)


class TestOrCriterion:
    """Tests for OrCriterion."""

    def test_both_match(self):
        """Test both criteria match."""
        criterion = OrCriterion(
            FromCriterion("sender@example.com"),
            SubjectCriterion("/test/i"),
        )
        email = make_email(from_address="sender@example.com", subject="Test email")

        assert criterion.matches(email)

    def test_left_only_match(self):
        """Test only left criterion matches."""
        criterion = OrCriterion(
            FromCriterion("sender@example.com"),
            SubjectCriterion("/newsletter/"),
        )
        email = make_email(from_address="sender@example.com", subject="Test email")

        assert criterion.matches(email)

    def test_right_only_match(self):
        """Test only right criterion matches."""
        criterion = OrCriterion(
            FromCriterion("other@example.com"),
            SubjectCriterion("/test/i"),
        )
        email = make_email(from_address="sender@example.com", subject="Test email")

        assert criterion.matches(email)

    def test_neither_match(self):
        """Test neither criterion matches."""
        criterion = OrCriterion(
            FromCriterion("other@example.com"),
            SubjectCriterion("/newsletter/"),
        )
        email = make_email(from_address="sender@example.com", subject="Test email")

        assert not criterion.matches(email)


class TestNotCriterion:
    """Tests for NotCriterion."""

    def test_not_matching(self):
        """Test NOT of matching criterion."""
        criterion = NotCriterion(FromCriterion("sender@example.com"))
        email = make_email(from_address="sender@example.com")

        assert not criterion.matches(email)

    def test_not_non_matching(self):
        """Test NOT of non-matching criterion."""
        criterion = NotCriterion(FromCriterion("other@example.com"))
        email = make_email(from_address="sender@example.com")

        assert criterion.matches(email)


class TestRequiresBody:
    """Tests for requires_body property."""

    def test_body_criterion_requires_body(self):
        """Test BodyCriterion requires body."""
        criterion = BodyCriterion("/test/")
        assert criterion.requires_body

    def test_from_criterion_no_body(self):
        """Test FromCriterion doesn't require body."""
        criterion = FromCriterion("test@example.com")
        assert not criterion.requires_body

    def test_subject_criterion_no_body(self):
        """Test SubjectCriterion doesn't require body."""
        criterion = SubjectCriterion("/test/")
        assert not criterion.requires_body

    def test_and_with_body(self):
        """Test AndCriterion with body criterion."""
        criterion = AndCriterion(
            FromCriterion("test@example.com"),
            BodyCriterion("/test/"),
        )
        assert criterion.requires_body

    def test_and_without_body(self):
        """Test AndCriterion without body criterion."""
        criterion = AndCriterion(
            FromCriterion("test@example.com"),
            SubjectCriterion("/test/"),
        )
        assert not criterion.requires_body

    def test_or_with_body(self):
        """Test OrCriterion with body criterion."""
        criterion = OrCriterion(
            FromCriterion("test@example.com"),
            BodyCriterion("/test/"),
        )
        assert criterion.requires_body

    def test_not_with_body(self):
        """Test NotCriterion with body criterion."""
        criterion = NotCriterion(BodyCriterion("/test/"))
        assert criterion.requires_body

    def test_not_without_body(self):
        """Test NotCriterion without body criterion."""
        criterion = NotCriterion(FromCriterion("test@example.com"))
        assert not criterion.requires_body
