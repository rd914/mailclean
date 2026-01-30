"""CLI commands for MailClean."""

import sys
from datetime import datetime, timedelta
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.prompt import Prompt, Confirm

from .config import Config, Account, KNOWN_PROVIDERS
from .imap_client import IMAPClient, IMAPError, MAILCLEAN_DELETED_FOLDER
from .query.parser import parse_query, ParseError
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
def search(query: str, folder: str, limit: int):
    """Search for emails matching a query."""
    config, account, password = get_client_from_config()

    # Validate query syntax
    try:
        criterion = parse_query(query)
    except ParseError as e:
        console.print(f"[red]Invalid query: {e.message}[/red]")
        return

    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Searching...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)
                uids = client.search_uids('ALL')

                progress.update(task, description=f"Found {len(uids)} emails, filtering...")

                # Fetch and filter emails
                matches = []
                for email_msg in client.fetch_emails(uids, include_body=False):
                    if criterion.matches(email_msg):
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
def preview(query: str, folder: str, page_size: int):
    """Preview emails matching a query with pagination."""
    config, account, password = get_client_from_config()

    try:
        criterion = parse_query(query)
    except ParseError as e:
        console.print(f"[red]Invalid query: {e.message}[/red]")
        return

    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Searching...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)
                uids = client.search_uids('ALL')

                progress.update(task, description=f"Found {len(uids)} emails, filtering...")

                matches = []
                for email_msg in client.fetch_emails(uids, include_body=False):
                    if criterion.matches(email_msg):
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
def delete(query: str, folder: str, yes: bool):
    """Delete emails matching a query (moves to MailClean-Deleted)."""
    config, account, password = get_client_from_config()

    try:
        criterion = parse_query(query)
    except ParseError as e:
        console.print(f"[red]Invalid query: {e.message}[/red]")
        return

    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Searching...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)
                uids = client.search_uids('ALL')

                progress.update(task, description=f"Found {len(uids)} emails, filtering...")

                matches = []
                for email_msg in client.fetch_emails(uids, include_body=False):
                    if criterion.matches(email_msg):
                        matches.append(email_msg)
        except IMAPError as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    if not matches:
        console.print("[yellow]No emails match your query.[/yellow]")
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


# Export command
@cli.command('export')
@click.argument('query')
@click.option('--format', '-f', 'fmt', type=click.Choice(['csv', 'json']), default='csv', help='Output format')
@click.option('--output', '-o', required=True, help='Output file path')
@click.option('--folder', default='INBOX', help='Folder to search in')
def export_cmd(query: str, fmt: str, output: str, folder: str):
    """Export matching emails to CSV or JSON."""
    config, account, password = get_client_from_config()

    try:
        criterion = parse_query(query)
    except ParseError as e:
        console.print(f"[red]Invalid query: {e.message}[/red]")
        return

    client = IMAPClient(account.server, account.port, account.email, password)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Searching...", total=None)

        try:
            with client.connection():
                client.select_folder(folder)
                uids = client.search_uids('ALL')

                progress.update(task, description=f"Found {len(uids)} emails, filtering...")

                matches = []
                for email_msg in client.fetch_emails(uids, include_body=False):
                    if criterion.matches(email_msg):
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
