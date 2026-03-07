# MailClean - Claude Notes

## Project Overview
Email cleanup CLI tool. Connects to IMAP, fetches emails client-side, filters them with a custom query language, and supports delete/restore/export operations.

## Running & Testing
```bash
# Run tests
pytest

# Run the CLI directly (installed as editable package)
mailclean <command>

# Install/reinstall
pip install -e ".[dev]"
```

## Key Files
- `mailclean/cli.py` — All CLI commands (Click-based)
- `mailclean/query/lexer.py` — Tokenizer for query language
- `mailclean/query/parser.py` — Recursive descent parser
- `mailclean/query/criteria.py` — Criterion classes that match `EmailMessage`
- `mailclean/query/evaluator.py` — `query_requires_body()` helper
- `mailclean/imap_client.py` — IMAP connection, fetch, move, delete
- `mailclean/models.py` — `EmailMessage` dataclass
- `mailclean/config.py` — Config/account storage (`~/.mailclean/config.json`), passwords in keyring
- `mailclean/utils.py` — Date parsing, regex helpers, spam scrubbing (homoglyphs, backspace tricks)

## CLI Commands
| Command | Description |
|---|---|
| `account add/list/remove/use` | Manage IMAP accounts |
| `folders` | List folders on server |
| `search <query>` | Search and display matches |
| `preview <query>` | Paginated preview of matches |
| `delete <query>` | Move matches to `MailClean-Deleted` |
| `purge` | Permanently delete emails >30 days from `MailClean-Deleted` |
| `restore [uids]` | Restore from `MailClean-Deleted` |
| `trash list` | List `MailClean-Deleted` contents |
| `top` | Top senders by count |
| `export <query>` | Export to CSV or JSON |
| `query save/list/run/delete` | Saved query management |

All query-taking commands accept `--folder/-f`, most accept `--scrub`.

## Query Language
Queries are a **single shell argument** — always quote them:
```bash
mailclean preview "to:foo@example.com OR from:/.*SPAM.*/"
```

### Syntax
```
from:pattern      # sender address
to:pattern        # To recipient
cc:pattern        # CC recipient
bcc:pattern       # BCC recipient
addressee:pattern # any recipient (To/CC/BCC)
subject:pattern   # subject line
body:pattern      # body text (triggers full fetch)
date:2024-01-15   # exact date
before:2024-01-15 # before date
after:2024-01-15  # after date
older-than:30d    # relative: d=days, w=weeks, m=months, y=years
newer-than:2w

AND / OR / NOT    # boolean operators (uppercase)
(...)             # grouping
```

Implicit AND between adjacent criteria. Patterns support `*` wildcards and `/regex/flags` syntax (`i`, `m`, `s` flags).

## Architecture Notes
- Emails are always fetched client-side (no server-side filtering). Full inbox is downloaded, then filtered in Python.
- `body:` queries trigger full RFC822 fetch; others fetch headers only (`RFC822.HEADER`).
- Deletion moves to `MailClean-Deleted` folder (soft delete). `purge` permanently deletes emails older than 30 days from that folder.
- `--scrub` flag normalizes text before matching: removes Unicode homoglyphs and processes backspace-trick obfuscation.
- Config stored at `~/.mailclean/config.json`; passwords in system keyring under service name `mailclean`.

## Known Provider Shortcuts
`gmail`, `yahoo`, `neomailbox` — server/port auto-filled on `account add`.
