"""CLI commands for MailClean."""

import sys
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.text import Text


def _get_key():
    """Read a single keypress, handling special keys cross-platform."""
    if sys.platform == 'win32':
        import msvcrt
        key = msvcrt.getwch()
        if key in ('\x00', '\xe0'):  # Special key prefix on Windows
            key2 = msvcrt.getwch()
            if key2 == 'H':
                return 'up'
            elif key2 == 'P':
                return 'down'
            elif key2 == 'K':
                return 'left'
            elif key2 == 'M':
                return 'right'
            return None
        return key
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            key = sys.stdin.read(1)
            if key == '\x1b':  # Escape sequence
                key2 = sys.stdin.read(1)
                if key2 == '[':
                    key3 = sys.stdin.read(1)
                    if key3 == 'A':
                        return 'up'
                    elif key3 == 'B':
                        return 'down'
                    elif key3 == 'C':
                        return 'right'
                    elif key3 == 'D':
                        return 'left'
                return 'escape'
            return key
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

from .config import Config, Account, KNOWN_PROVIDERS
from .imap_client import IMAPClient, IMAPError, MAILCLEAN_DELETED_FOLDER
from .index import MailIndex, INDEX_DIR, _folder_to_filename, load_and_sync
from .query.parser import parse_query, ParseError
from .query.evaluator import query_requires_body, query_requires_headers
from .export import export_to_csv, export_to_json

console = Console()


def get_client_from_config() -> tuple[Config, Account, str]:
    """Get IMAP client info from config."""
    config = Config.load()
    account = config.get_active_account()

    if not account:
        console.print("[red]No active account. Use 'mailclean account add' first.[/red]")
        sys.exit(1)

    password = account.get_password()
    if not password:
        console.print("[red]No password stored for account. Use 'mailclean account add' to reconfigure.[/red]")
        sys.exit(1)

    return config, account, password


@click.group()
@click.version_option()
def cli():
    """MailClean - Email cleanup with flexible query language."""
    pass


# Account management commands
@cli.group()
def account():
    """Manage email accounts."""
    pass


@account.command('add')
@click.argument('name')
def account_add(name: str):
    """Add a new email account."""
    config = Config.load()

    if name in config.accounts:
        if not Confirm.ask(f"Account '{name}' already exists. Overwrite?"):
            return

    console.print("\n[bold]Add Email Account[/bold]\n")

    # Ask for provider
    console.print("Known providers: gmail, yahoo, neomailbox, custom")
    provider = Prompt.ask("Provider", default="custom").lower()

    if provider in KNOWN_PROVIDERS:
        server = KNOWN_PROVIDERS[provider]['server']
        port = KNOWN_PROVIDERS[provider]['port']
        console.print(f"Using {server}:{port}")
    else:
        server = Prompt.ask("IMAP server")
        port = int(Prompt.ask("Port", default="993"))

    email_addr = Prompt.ask("Email address")
    password = Prompt.ask("Password (app-specific recommended)", password=True)

    # Test connection
    console.print("\nTesting connection...")
    client = IMAPClient(server, port, email_addr, password)

    try:
        with client.connection():
            folders = client.list_folders()
            console.print(f"[green]Connected successfully! Found {len(folders)} folders.[/green]")
    except IMAPError as e:
        console.print(f"[red]Connection failed: {e}[/red]")
        if not Confirm.ask("Save account anyway?"):
            return

    # Save account
    account_obj = Account(
        name=name,
        email=email_addr,
        server=server,
        port=port,
    )
    config.add_account(account_obj, password)
    console.print(f"\n[green]Account '{name}' added and set as active.[/green]")


@account.command('list')
def account_list():
    """List all configured accounts."""
    config = Config.load()

    if not config.accounts:
        console.print("No accounts configured. Use 'mailclean account add' to add one.")
        return

    table = Table(title="Email Accounts")
    table.add_column("Name", style="cyan")
    table.add_column("Email", style="green")
    table.add_column("Server", style="yellow")
    table.add_column("Active", style="magenta")

    for name, acc in config.accounts.items():
        is_active = "Yes" if name == config.active_account else ""
        table.add_row(name, acc.email, f"{acc.server}:{acc.port}", is_active)

    console.print(table)


@account.command('remove')
@click.argument('name')
def account_remove(name: str):
    """Remove an email account."""
    config = Config.load()

    if name not in config.accounts:
        console.print(f"[red]Account '{name}' not found.[/red]")
        return

    if Confirm.ask(f"Remove account '{name}'?"):
        config.remove_account(name)
        console.print(f"[green]Account '{name}' removed.[/green]")


@account.command('use')
@click.argument('name')
def account_use(name: str):
    """Set the active account."""
    config = Config.load()

    if config.set_active_account(name):
        console.print(f"[green]Active account set to '{name}'.[/green]")
    else:
        console.print(f"[red]Account '{name}' not found.[/red]")


# Folder command
@cli.command('folders')
def folders():
    """List folders on the mail server."""
    config, account, password = get_client_from_config()

    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Connecting...", total=None)

        try:
            with client.connection():
                folder_list = client.list_folders()
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    console.print(f"\n[bold]Folders on {account.email}:[/bold]\n")
    for folder in sorted(folder_list):
        console.print(f"  {folder}")
    console.print(f"\n[dim]Total: {len(folder_list)} folders[/dim]")


# Search command
@cli.command('search')
@click.argument('query')
@click.option('--folder', '-f', default='INBOX', help='Folder to search in')
@click.option('--limit', '-l', default=100, help='Maximum results to return')
@click.option('--scrub', is_flag=True, help='Normalize text to detect spam obfuscation')
def search(query: str, folder: str, limit: int, scrub: bool):
    """Search for emails matching a query."""
    config, account, password = get_client_from_config()

    # Validate query syntax
    try:
        criterion = parse_query(query)
    except ParseError as e:
        console.print(f"[red]Invalid query: {e.message}[/red]")
        return

    needs_body = query_requires_body(query)
    needs_headers = query_requires_headers(query)
    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)

                def _update(desc: str) -> None:
                    progress.update(task, description=desc)

                index = load_and_sync(account.name, folder, client, on_progress=_update)

                progress.update(task, description=f"Filtering {index.email_count} emails...")

                matches = []
                if not needs_body and not needs_headers:
                    for email_msg in index.iter_emails():
                        match_target = email_msg.scrubbed() if scrub else email_msg
                        if criterion.matches(match_target):
                            matches.append(email_msg)
                            if len(matches) >= limit:
                                break
                else:
                    for email_msg in client.fetch_emails(index.get_uids(), include_body=needs_body):
                        match_target = email_msg.scrubbed() if scrub else email_msg
                        if criterion.matches(match_target):
                            matches.append(email_msg)
                            if len(matches) >= limit:
                                break
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    if not matches:
        console.print("[yellow]No emails match your query.[/yellow]")
        return

    table = Table(title=f"Search Results ({len(matches)} matches)")
    table.add_column("UID", style="dim")
    table.add_column("Date", style="cyan")
    table.add_column("From", style="green", max_width=30)
    table.add_column("Subject", style="yellow", max_width=50)

    for email_msg in matches:
        date_str = email_msg.date.strftime('%Y-%m-%d %H:%M') if email_msg.date else 'Unknown'
        table.add_row(
            str(email_msg.uid),
            date_str,
            email_msg.from_address[:30],
            email_msg.subject[:50] if email_msg.subject else '(no subject)',
        )

    console.print(table)


# Preview command
@cli.command('preview')
@click.argument('query')
@click.option('--folder', '-f', default='INBOX', help='Folder to search in')
@click.option('--page-size', '-p', default=20, help='Results per page')
@click.option('--scrub', is_flag=True, help='Normalize text to detect spam obfuscation')
def preview(query: str, folder: str, page_size: int, scrub: bool):
    """Preview emails matching a query with pagination."""
    config, account, password = get_client_from_config()

    try:
        criterion = parse_query(query)
    except ParseError as e:
        console.print(f"[red]Invalid query: {e.message}[/red]")
        return

    needs_body = query_requires_body(query)
    needs_headers = query_requires_headers(query)
    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)

                def _update(desc: str) -> None:
                    progress.update(task, description=desc)

                index = load_and_sync(account.name, folder, client, on_progress=_update)

                progress.update(task, description=f"Filtering {index.email_count} emails...")

                matches = []
                if not needs_body and not needs_headers:
                    for email_msg in index.iter_emails():
                        match_target = email_msg.scrubbed() if scrub else email_msg
                        if criterion.matches(match_target):
                            matches.append(email_msg)
                else:
                    for email_msg in client.fetch_emails(index.get_uids(), include_body=needs_body):
                        match_target = email_msg.scrubbed() if scrub else email_msg
                        if criterion.matches(match_target):
                            matches.append(email_msg)
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    if not matches:
        console.print("[yellow]No emails match your query.[/yellow]")
        return

    # Paginated display
    total_pages = (len(matches) + page_size - 1) // page_size
    current_page = 0

    while True:
        start = current_page * page_size
        end = min(start + page_size, len(matches))
        page_emails = matches[start:end]

        console.clear()
        console.print(f"\n[bold]Preview: {query}[/bold]")
        console.print(f"[dim]Page {current_page + 1}/{total_pages} | Total: {len(matches)} emails[/dim]\n")

        table = Table()
        table.add_column("UID", style="dim")
        table.add_column("Date", style="cyan")
        table.add_column("From", style="green", max_width=30)
        table.add_column("Subject", style="yellow", max_width=50)

        for email_msg in page_emails:
            date_str = email_msg.date.strftime('%Y-%m-%d %H:%M') if email_msg.date else 'Unknown'
            table.add_row(
                str(email_msg.uid),
                date_str,
                email_msg.from_address[:30],
                email_msg.subject[:50] if email_msg.subject else '(no subject)',
            )

        console.print(table)

        console.print("\n[dim]n=next, p=prev, q=quit[/dim]")
        choice = Prompt.ask("Action", choices=['n', 'p', 'q'], default='n')

        if choice == 'q':
            break
        elif choice == 'n' and current_page < total_pages - 1:
            current_page += 1
        elif choice == 'p' and current_page > 0:
            current_page -= 1


# Delete command
@cli.command('delete')
@click.argument('query')
@click.option('--folder', '-f', default='INBOX', help='Folder to delete from')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
@click.option('--scrub', is_flag=True, help='Normalize text to detect spam obfuscation')
@click.option('--select', '-s', is_flag=True, help='Interactively select emails to delete')
def delete(query: str, folder: str, yes: bool, scrub: bool, select: bool):
    """Delete emails matching a query (moves to MailClean-Deleted)."""
    config, account, password = get_client_from_config()

    try:
        criterion = parse_query(query)
    except ParseError as e:
        console.print(f"[red]Invalid query: {e.message}[/red]")
        return

    needs_body = query_requires_body(query)
    needs_headers = query_requires_headers(query)
    client = IMAPClient(account.server, account.port, account.email, password)

    # Load index outside the connection so we can invalidate it after deletion
    index = MailIndex(account.name, folder)
    index.load()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)

                def _update(desc: str) -> None:
                    progress.update(task, description=desc)

                index = load_and_sync(account.name, folder, client, on_progress=_update)

                progress.update(task, description=f"Filtering {index.email_count} emails...")

                matches = []
                if not needs_body and not needs_headers:
                    for email_msg in index.iter_emails():
                        match_target = email_msg.scrubbed() if scrub else email_msg
                        if criterion.matches(match_target):
                            matches.append(email_msg)
                else:
                    for email_msg in client.fetch_emails(index.get_uids(), include_body=needs_body):
                        match_target = email_msg.scrubbed() if scrub else email_msg
                        if criterion.matches(match_target):
                            matches.append(email_msg)
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    if not matches:
        console.print("[yellow]No emails match your query.[/yellow]")
        return

    # Interactive selection mode
    if select:
        selected_uids = set()
        page_size = 20
        total_pages = (len(matches) + page_size - 1) // page_size
        current_page = 0
        cursor = 0  # Position within current page

        def render_selection_table():
            """Render the selection table with cursor highlight."""
            start = current_page * page_size
            end = min(start + page_size, len(matches))
            page_emails = matches[start:end]

            table = Table(title=f"Select emails to delete: {query}")
            table.add_column("", style="dim", width=2)  # Cursor indicator
            table.add_column("Sel", style="magenta", width=3)
            table.add_column("Date", style="cyan")
            table.add_column("From", style="green", max_width=30)
            table.add_column("Subject", style="yellow", max_width=50)

            for i, email_msg in enumerate(page_emails):
                is_selected = email_msg.uid in selected_uids
                sel_marker = "[X]" if is_selected else "[ ]"
                cursor_marker = ">" if i == cursor else " "
                date_str = email_msg.date.strftime('%Y-%m-%d %H:%M') if email_msg.date else 'Unknown'

                # Highlight the cursor row
                if i == cursor:
                    table.add_row(
                        cursor_marker,
                        sel_marker,
                        f"[bold]{date_str}[/bold]",
                        f"[bold]{email_msg.from_address[:30]}[/bold]",
                        f"[bold]{(email_msg.subject[:50] if email_msg.subject else '(no subject)')}[/bold]",
                    )
                else:
                    table.add_row(
                        cursor_marker,
                        sel_marker,
                        date_str,
                        email_msg.from_address[:30],
                        email_msg.subject[:50] if email_msg.subject else '(no subject)',
                    )

            return table

        console.clear()
        with Live(console=console, refresh_per_second=10, screen=False) as live:
            while True:
                start = current_page * page_size
                end = min(start + page_size, len(matches))
                page_count = end - start

                # Build display
                output = Text()
                output.append(f"\nPage {current_page + 1}/{total_pages} | Total: {len(matches)} | Selected: {len(selected_uids)}\n\n", style="dim")

                live.update(output)
                console.print(render_selection_table())
                console.print("\n[dim]↑/↓=move | space=toggle | a=all | z=none | ←/→=page | d=delete | q=quit[/dim]")

                key = _get_key()

                if key == 'q':
                    live.stop()
                    console.print("[yellow]Cancelled.[/yellow]")
                    return
                elif key == 'd':
                    live.stop()
                    break
                elif key == 'up' or key == 'k':
                    if cursor > 0:
                        cursor -= 1
                    elif current_page > 0:
                        current_page -= 1
                        cursor = page_size - 1
                elif key == 'down' or key == 'j':
                    if cursor < page_count - 1:
                        cursor += 1
                    elif current_page < total_pages - 1:
                        current_page += 1
                        cursor = 0
                elif key == 'left' and current_page > 0:
                    current_page -= 1
                    cursor = 0
                elif key == 'right' and current_page < total_pages - 1:
                    current_page += 1
                    cursor = 0
                elif key == ' ':  # Space to toggle
                    email_msg = matches[start + cursor]
                    if email_msg.uid in selected_uids:
                        selected_uids.discard(email_msg.uid)
                    else:
                        selected_uids.add(email_msg.uid)
                    # Move to next line
                    if cursor < page_count - 1:
                        cursor += 1
                    elif current_page < total_pages - 1:
                        current_page += 1
                        cursor = 0
                elif key == 'a':
                    # Select all on current page
                    for email_msg in matches[start:end]:
                        selected_uids.add(email_msg.uid)
                elif key == 'z':
                    # Deselect all on current page
                    for email_msg in matches[start:end]:
                        selected_uids.discard(email_msg.uid)
                elif key == '\r' or key == '\n':  # Enter also toggles
                    email_msg = matches[start + cursor]
                    if email_msg.uid in selected_uids:
                        selected_uids.discard(email_msg.uid)
                    else:
                        selected_uids.add(email_msg.uid)
                    # Move to next line
                    if cursor < page_count - 1:
                        cursor += 1
                    elif current_page < total_pages - 1:
                        current_page += 1
                        cursor = 0

                console.clear()

        # Filter matches to only selected
        matches = [m for m in matches if m.uid in selected_uids]
        if not matches:
            console.print("[yellow]No emails selected.[/yellow]")
            return

    # Show summary
    table = Table(title=f"Emails to Delete ({len(matches)} matches)")
    table.add_column("Date", style="cyan")
    table.add_column("From", style="green", max_width=30)
    table.add_column("Subject", style="yellow", max_width=50)

    for email_msg in matches[:10]:
        date_str = email_msg.date.strftime('%Y-%m-%d %H:%M') if email_msg.date else 'Unknown'
        table.add_row(
            date_str,
            email_msg.from_address[:30],
            email_msg.subject[:50] if email_msg.subject else '(no subject)',
        )

    if len(matches) > 10:
        table.add_row("...", f"({len(matches) - 10} more)", "...")

    console.print(table)

    if not yes:
        if not Confirm.ask(f"\nMove {len(matches)} emails to MailClean-Deleted?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    # Perform deletion
    match_uids = [m.uid for m in matches]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Moving to MailClean-Deleted...", total=None)

        try:
            with client.connection():
                moved = client.move_to_mailclean_deleted(match_uids, folder)
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    console.print(f"[green]Moved {moved} emails to MailClean-Deleted.[/green]")
    console.print("[dim]Use 'mailclean restore' to recover emails within 30 days.[/dim]")

    if moved > 0:
        index.invalidate_uids(match_uids)


# Purge command
@cli.command('purge')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
def purge(yes: bool):
    """Permanently delete emails older than 30 days from MailClean-Deleted."""
    config, account, password = get_client_from_config()

    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning MailClean-Deleted...", total=None)

        try:
            with client.connection():
                try:
                    client.select_folder(MAILCLEAN_DELETED_FOLDER)
                except IMAPError:
                    console.print("[yellow]MailClean-Deleted folder does not exist.[/yellow]")
                    return

                old_uids = client.get_emails_older_than(30)
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    if not old_uids:
        console.print("[green]No emails older than 30 days in MailClean-Deleted.[/green]")
        return

    console.print(f"\n[bold]Found {len(old_uids)} emails older than 30 days.[/bold]")

    if not yes:
        if not Confirm.ask("Permanently delete these emails?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Permanently deleting...", total=None)

        try:
            with client.connection():
                client.select_folder(MAILCLEAN_DELETED_FOLDER)
                deleted = client.permanently_delete(old_uids)
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    console.print(f"[green]Permanently deleted {deleted} emails.[/green]")


# Restore command
@cli.command('restore')
@click.argument('target', required=False)
@click.option('--to', '-t', default='INBOX', help='Folder to restore to')
def restore(target: Optional[str], to: str):
    """Restore emails from MailClean-Deleted."""
    config, account, password = get_client_from_config()

    client = IMAPClient(account.server, account.port, account.email, password)

    if target:
        # Restore specific UIDs
        try:
            uids = [int(uid.strip()) for uid in target.split(',')]
        except ValueError:
            console.print("[red]Invalid UID format. Provide comma-separated UIDs.[/red]")
            return
    else:
        # Show list and let user select
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Listing deleted emails...", total=None)

            try:
                with client.connection():
                    try:
                        client.select_folder(MAILCLEAN_DELETED_FOLDER)
                    except IMAPError:
                        console.print("[yellow]MailClean-Deleted folder does not exist.[/yellow]")
                        return

                    all_uids = client.search_uids('ALL')
                    emails = list(client.fetch_emails(all_uids, include_body=False))
            except IMAPError as e:
                console.print(f"[red]Error: {e}[/red]")
                return

        if not emails:
            console.print("[green]MailClean-Deleted is empty.[/green]")
            return

        table = Table(title="Deleted Emails")
        table.add_column("UID", style="dim")
        table.add_column("Date", style="cyan")
        table.add_column("From", style="green", max_width=30)
        table.add_column("Subject", style="yellow", max_width=50)

        for email_msg in emails[:20]:
            date_str = email_msg.date.strftime('%Y-%m-%d %H:%M') if email_msg.date else 'Unknown'
            table.add_row(
                str(email_msg.uid),
                date_str,
                email_msg.from_address[:30],
                email_msg.subject[:50] if email_msg.subject else '(no subject)',
            )

        if len(emails) > 20:
            console.print(f"[dim]({len(emails) - 20} more emails not shown)[/dim]")

        console.print(table)

        uid_input = Prompt.ask("\nEnter UIDs to restore (comma-separated) or 'all'")
        if uid_input.lower() == 'all':
            uids = [e.uid for e in emails]
        else:
            try:
                uids = [int(uid.strip()) for uid in uid_input.split(',')]
            except ValueError:
                console.print("[red]Invalid UID format.[/red]")
                return

    # Perform restoration
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Restoring...", total=None)

        try:
            with client.connection():
                restored = client.restore_from_mailclean_deleted(uids, to)
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    console.print(f"[green]Restored {restored} emails to {to}.[/green]")


# Trash list command
@cli.group('trash')
def trash():
    """Manage MailClean-Deleted folder."""
    pass


@trash.command('list')
def trash_list():
    """List contents of MailClean-Deleted folder."""
    config, account, password = get_client_from_config()

    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching deleted emails...", total=None)

        try:
            with client.connection():
                try:
                    client.select_folder(MAILCLEAN_DELETED_FOLDER)
                except IMAPError:
                    console.print("[yellow]MailClean-Deleted folder does not exist.[/yellow]")
                    return

                uids = client.search_uids('ALL')
                emails = list(client.fetch_emails(uids, include_body=False))
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    if not emails:
        console.print("[green]MailClean-Deleted is empty.[/green]")
        return

    table = Table(title=f"MailClean-Deleted ({len(emails)} emails)")
    table.add_column("UID", style="dim")
    table.add_column("Date", style="cyan")
    table.add_column("From", style="green", max_width=30)
    table.add_column("Subject", style="yellow", max_width=50)

    for email_msg in emails:
        date_str = email_msg.date.strftime('%Y-%m-%d %H:%M') if email_msg.date else 'Unknown'
        table.add_row(
            str(email_msg.uid),
            date_str,
            email_msg.from_address[:30],
            email_msg.subject[:50] if email_msg.subject else '(no subject)',
        )

    console.print(table)


# Top senders command
@cli.command('top')
@click.option('--folder', '-f', default='INBOX', help='Folder to analyze')
@click.option('--limit', '-l', default=20, help='Number of top senders to show')
@click.option('--query', '-q', default=None, help='Optional query to filter emails first')
@click.option('--scrub', is_flag=True, help='Normalize text to detect spam obfuscation')
def top(folder: str, limit: int, query: Optional[str], scrub: bool):
    """Show top senders by email count."""
    config, account, password = get_client_from_config()

    # Parse query if provided
    criterion = None
    needs_body = False
    if query:
        try:
            criterion = parse_query(query)
            needs_body = query_requires_body(query)
        except ParseError as e:
            console.print(f"[red]Invalid query: {e.message}[/red]")
            return

    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)

                def _update(desc: str) -> None:
                    progress.update(task, description=desc)

                index = load_and_sync(account.name, folder, client, on_progress=_update)

                progress.update(task, description=f"Analyzing {index.email_count} emails...")

                sender_counts: Counter[str] = Counter()
                for email_msg in index.iter_emails():
                    if criterion:
                        match_target = email_msg.scrubbed() if scrub else email_msg
                        if not criterion.matches(match_target):
                            continue
                    sender_counts[email_msg.from_address] += 1
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    if not sender_counts:
        console.print("[yellow]No emails found.[/yellow]")
        return

    total_emails = sum(sender_counts.values())
    top_senders = sender_counts.most_common(limit)

    table = Table(title=f"Top {len(top_senders)} Senders in {folder} ({total_emails} total emails)")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Count", style="cyan", justify="right")
    table.add_column("%", style="magenta", justify="right")
    table.add_column("Sender", style="green")

    for rank, (sender, count) in enumerate(top_senders, 1):
        pct = (count / total_emails) * 100
        table.add_row(
            str(rank),
            str(count),
            f"{pct:.1f}%",
            sender,
        )

    console.print(table)

    # Show summary
    top_total = sum(count for _, count in top_senders)
    top_pct = (top_total / total_emails) * 100
    console.print(f"\n[dim]Top {len(top_senders)} senders account for {top_total} emails ({top_pct:.1f}% of total)[/dim]")


# Export command
@cli.command('export')
@click.argument('query')
@click.option('--format', '-f', 'fmt', type=click.Choice(['csv', 'json']), default='csv', help='Output format')
@click.option('--output', '-o', required=True, help='Output file path')
@click.option('--folder', default='INBOX', help='Folder to search in')
@click.option('--scrub', is_flag=True, help='Normalize text to detect spam obfuscation')
def export_cmd(query: str, fmt: str, output: str, folder: str, scrub: bool):
    """Export matching emails to CSV or JSON."""
    config, account, password = get_client_from_config()

    try:
        criterion = parse_query(query)
    except ParseError as e:
        console.print(f"[red]Invalid query: {e.message}[/red]")
        return

    needs_body = query_requires_body(query)
    needs_headers = query_requires_headers(query)
    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)

                def _update(desc: str) -> None:
                    progress.update(task, description=desc)

                index = load_and_sync(account.name, folder, client, on_progress=_update)

                progress.update(task, description=f"Filtering {index.email_count} emails...")

                matches = []
                if not needs_body and not needs_headers:
                    for email_msg in index.iter_emails():
                        match_target = email_msg.scrubbed() if scrub else email_msg
                        if criterion.matches(match_target):
                            matches.append(email_msg)
                else:
                    for email_msg in client.fetch_emails(index.get_uids(), include_body=needs_body):
                        match_target = email_msg.scrubbed() if scrub else email_msg
                        if criterion.matches(match_target):
                            matches.append(email_msg)
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    if not matches:
        console.print("[yellow]No emails match your query.[/yellow]")
        return

    # Export
    if fmt == 'csv':
        count = export_to_csv(matches, output)
    else:
        count = export_to_json(matches, output)

    console.print(f"[green]Exported {count} emails to {output}[/green]")


# Index management commands
@cli.group('index')
def index_cmd():
    """Manage the local email index."""
    pass


@index_cmd.command('status')
@click.option('--folder', '-f', default='INBOX', help='Folder to check')
def index_status(folder: str):
    """Show index status for the active account and folder."""
    config, account, _ = get_client_from_config()

    index = MailIndex(account.name, folder)
    loaded = index.load()

    if not loaded:
        console.print(f"[yellow]No index found for {account.email} / {folder}[/yellow]")
        console.print("[dim]It will be built automatically on the next search, preview, delete, or export.[/dim]")
        return

    from .index import DEFAULT_MAX_AGE_DAYS
    table = Table(title=f"Index: {account.email} / {folder}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Emails indexed", str(index.email_count))
    table.add_row(
        "First built",
        index.built_at.strftime('%Y-%m-%d %H:%M UTC') if index.built_at else "—",
    )
    table.add_row(
        "Last synced",
        index.last_synced_at.strftime('%Y-%m-%d %H:%M UTC') if index.last_synced_at else "—",
    )
    table.add_row(
        "Last full rebuild",
        index.full_rebuild_at.strftime('%Y-%m-%d %H:%M UTC') if index.full_rebuild_at else "—",
    )
    table.add_row(
        "Full rebuild due",
        "[red]Yes[/red]" if index.needs_full_rebuild() else f"No (every {DEFAULT_MAX_AGE_DAYS} days)",
    )
    table.add_row("Index file", str(index.path))

    console.print(table)


@index_cmd.command('rebuild')
@click.option('--folder', '-f', default='INBOX', help='Folder to rebuild index for')
def index_rebuild(folder: str):
    """Force a full index rebuild for a folder."""
    config, account, password = get_client_from_config()

    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Connecting...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)

                def _update(desc: str) -> None:
                    progress.update(task, description=desc)

                index = MailIndex(account.name, folder)
                index.load()
                count = index.full_rebuild(client, on_progress=_update)
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    console.print(f"[green]Index rebuilt: {count} emails indexed for {account.email} / {folder}[/green]")


@index_cmd.command('clear')
@click.option('--folder', '-f', default=None, help='Folder to clear (omit for all folders)')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
def index_clear(folder: Optional[str], yes: bool):
    """Delete local index files for the active account."""
    config, account, _ = get_client_from_config()

    account_dir = INDEX_DIR / account.name

    if folder:
        target = account_dir / _folder_to_filename(folder)
        if not target.exists():
            console.print(f"[yellow]No index found for {account.email} / {folder}[/yellow]")
            return
        if not yes and not Confirm.ask(f"Delete index for {account.email} / {folder}?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return
        target.unlink()
        console.print(f"[green]Index cleared for {folder}.[/green]")
    else:
        if not account_dir.exists():
            console.print("[yellow]No index files found.[/yellow]")
            return
        files = list(account_dir.glob('*.json'))
        if not files:
            console.print("[yellow]No index files found.[/yellow]")
            return
        if not yes and not Confirm.ask(f"Delete all {len(files)} index file(s) for {account.email}?"):
            console.print("[yellow]Cancelled.[/yellow]")
            return
        for f in files:
            f.unlink()
        console.print(f"[green]Cleared {len(files)} index file(s) for {account.email}.[/green]")


# Saved queries
@cli.group('query')
def query_cmd():
    """Manage saved queries."""
    pass


@query_cmd.command('save')
@click.argument('name')
@click.argument('query')
def query_save(name: str, query: str):
    """Save a query for later use."""
    # Validate query
    try:
        parse_query(query)
    except ParseError as e:
        console.print(f"[red]Invalid query: {e.message}[/red]")
        return

    config = Config.load()
    config.save_query(name, query)
    console.print(f"[green]Query '{name}' saved.[/green]")


@query_cmd.command('list')
def query_list():
    """List saved queries."""
    config = Config.load()

    if not config.saved_queries:
        console.print("No saved queries. Use 'mailclean query save' to add one.")
        return

    table = Table(title="Saved Queries")
    table.add_column("Name", style="cyan")
    table.add_column("Query", style="green")

    for name, q in config.saved_queries.items():
        table.add_row(name, q.query)

    console.print(table)


@query_cmd.command('run')
@click.argument('name')
@click.option('--folder', '-f', default='INBOX', help='Folder to search in')
@click.option('--limit', '-l', default=100, help='Maximum results')
def query_run(name: str, folder: str, limit: int):
    """Run a saved query."""
    config = Config.load()
    saved = config.get_query(name)

    if not saved:
        console.print(f"[red]Query '{name}' not found.[/red]")
        return

    console.print(f"[dim]Running: {saved.query}[/dim]\n")

    # Invoke search with the saved query
    ctx = click.get_current_context()
    ctx.invoke(search, query=saved.query, folder=folder, limit=limit)


@query_cmd.command('delete')
@click.argument('name')
def query_delete(name: str):
    """Delete a saved query."""
    config = Config.load()

    if config.delete_query(name):
        console.print(f"[green]Query '{name}' deleted.[/green]")
    else:
        console.print(f"[red]Query '{name}' not found.[/red]")
