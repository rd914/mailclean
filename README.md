# MailClean

A Python CLI application for deleting emails from IMAP mail servers with a flexible query language, preview capability, and 30-day restore window.

## Features

- **Flexible query language**: Search emails using criteria with AND/OR/NOT operators and parentheses grouping
- **Safe deletion**: Emails are moved to `MailClean-Deleted` folder with 30-day restore window
- **Multiple providers**: Works with Gmail, Yahoo Mail, Neomailbox, or any IMAP server
- **Export**: Export search results to CSV or JSON
- **Saved queries**: Save frequently used queries for quick access

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# Add an email account
mailclean account add myaccount

# List folders
mailclean folders

# Search for emails
mailclean search "from:*@newsletter.com AND older-than:30d"

# Preview emails before deleting
mailclean preview "subject:/unsubscribe/i"

# Delete matching emails (moves to MailClean-Deleted)
mailclean delete "from:spam@example.com"

# Restore deleted emails
mailclean restore

# Permanently delete emails older than 30 days
mailclean purge
```

## Query Language

### Basic Criteria

```
from:user@example.com              # Match sender
to:recipient@example.com           # Match To recipient
cc:someone@example.com             # Match CC recipient
bcc:hidden@example.com             # Match BCC recipient
addressee:anyone@example.com       # Match To, CC, or BCC
```

### Date Criteria

```
date:2024-06-15                    # Exact date
before:2024-01-01                  # Before date
after:2023-06-01                   # After date
older-than:30d                     # Relative: d=days, w=weeks, m=months
newer-than:1w                      # Within last week
```

### Regex Matching

```
subject:/newsletter/i              # Case-insensitive match
body:/unsubscribe.*click/i         # Body content search
```

### Combining Criteria

```
from:*@spam.com AND older-than:90d
(from:news@site.com OR from:updates@site.com) AND older-than:30d
NOT from:important@work.com
```

### Wildcards

Use `*` as a wildcard in email addresses:

```
from:*@spam.com                    # Any sender from spam.com
from:newsletter@*                  # Newsletter from any domain
```

## CLI Commands

### Account Management

```bash
mailclean account add <name>       # Add account (interactive)
mailclean account list             # List all accounts
mailclean account remove <name>    # Remove an account
mailclean account use <name>       # Set active account
```

### Search and Preview

```bash
mailclean search <query> [--folder INBOX] [--limit 100]
mailclean preview <query> [--folder INBOX] [--page-size 20]
```

### Delete and Restore

```bash
mailclean delete <query> [--folder INBOX] [--yes]
mailclean restore [<uids>] [--to INBOX]
mailclean trash list
mailclean purge [--yes]
```

### Export

```bash
mailclean export <query> --format csv --output results.csv
mailclean export <query> --format json --output results.json
```

### Saved Queries

```bash
mailclean query save <name> "<query>"
mailclean query list
mailclean query run <name> [--folder INBOX]
mailclean query delete <name>
```

### Folders

```bash
mailclean folders                  # List all folders
```

## Supported Providers

| Provider    | Server                  | Port | Notes                          |
|-------------|-------------------------|------|--------------------------------|
| Gmail       | imap.gmail.com          | 993  | Requires app-specific password |
| Yahoo       | imap.mail.yahoo.com     | 993  | Requires app-specific password |
| Neomailbox  | mail.neomailbox.com     | 993  | Standard IMAP                  |
| Custom      | User-specified          | 993  | Any IMAP server                |

## Configuration

Configuration is stored in `~/.mailclean/config.json`. Passwords are stored securely using the system keyring.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/
```

## License

MIT
