"""Export functionality for email data."""

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import EmailMessage


def export_to_csv(emails: Iterable[EmailMessage], output_path: str | Path) -> int:
    """
    Export emails to CSV format.

    Args:
        emails: Iterable of EmailMessage objects
        output_path: Path to the output CSV file

    Returns:
        Number of emails exported
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ['message_id', 'date', 'from', 'to', 'subject', 'folder']
    count = 0

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for email_msg in emails:
            writer.writerow(email_msg.to_csv_row())
            count += 1

    return count


def export_to_json(emails: Iterable[EmailMessage], output_path: str | Path) -> int:
    """
    Export emails to JSON format.

    Args:
        emails: Iterable of EmailMessage objects
        output_path: Path to the output JSON file

    Returns:
        Number of emails exported
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    email_list = []
    for email_msg in emails:
        email_list.append(email_msg.to_dict())

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(email_list, f, indent=2, default=str)

    return len(email_list)
