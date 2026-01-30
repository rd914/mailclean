"""Configuration management for MailClean."""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import keyring

CONFIG_DIR = Path.home() / '.mailclean'
CONFIG_FILE = CONFIG_DIR / 'config.json'
KEYRING_SERVICE = 'mailclean'

# Known IMAP server settings
KNOWN_PROVIDERS = {
    'gmail': {
        'server': 'imap.gmail.com',
        'port': 993,
    },
    'yahoo': {
        'server': 'imap.mail.yahoo.com',
        'port': 993,
    },
    'neomailbox': {
        'server': 'mail.neomailbox.com',
        'port': 993,
    },
}


@dataclass
class Account:
    """IMAP account configuration."""

    name: str
    email: str
    server: str
    port: int = 993
    use_ssl: bool = True

    def get_password(self) -> Optional[str]:
        """Retrieve password from system keyring."""
        return keyring.get_password(KEYRING_SERVICE, self.name)

    def set_password(self, password: str) -> None:
        """Store password in system keyring."""
        keyring.set_password(KEYRING_SERVICE, self.name, password)

    def delete_password(self) -> None:
        """Remove password from system keyring."""
        try:
            keyring.delete_password(KEYRING_SERVICE, self.name)
        except keyring.errors.PasswordDeleteError:
            pass


@dataclass
class SavedQuery:
    """A saved search query."""

    name: str
    query: str


@dataclass
class Config:
    """Application configuration."""

    accounts: dict[str, Account] = field(default_factory=dict)
    active_account: Optional[str] = None
    saved_queries: dict[str, SavedQuery] = field(default_factory=dict)

    @classmethod
    def load(cls) -> 'Config':
        """Load configuration from disk."""
        if not CONFIG_FILE.exists():
            return cls()

        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)

            config = cls()

            # Load accounts
            for name, acc_data in data.get('accounts', {}).items():
                config.accounts[name] = Account(
                    name=acc_data['name'],
                    email=acc_data['email'],
                    server=acc_data['server'],
                    port=acc_data.get('port', 993),
                    use_ssl=acc_data.get('use_ssl', True),
                )

            # Load active account
            config.active_account = data.get('active_account')

            # Load saved queries
            for name, query_data in data.get('saved_queries', {}).items():
                config.saved_queries[name] = SavedQuery(
                    name=query_data['name'],
                    query=query_data['query'],
                )

            return config

        except (json.JSONDecodeError, KeyError):
            return cls()

    def save(self) -> None:
        """Save configuration to disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            'accounts': {
                name: {
                    'name': acc.name,
                    'email': acc.email,
                    'server': acc.server,
                    'port': acc.port,
                    'use_ssl': acc.use_ssl,
                }
                for name, acc in self.accounts.items()
            },
            'active_account': self.active_account,
            'saved_queries': {
                name: {'name': q.name, 'query': q.query}
                for name, q in self.saved_queries.items()
            },
        }

        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def add_account(self, account: Account, password: str) -> None:
        """Add or update an account."""
        self.accounts[account.name] = account
        account.set_password(password)
        if self.active_account is None:
            self.active_account = account.name
        self.save()

    def remove_account(self, name: str) -> bool:
        """Remove an account."""
        if name not in self.accounts:
            return False

        self.accounts[name].delete_password()
        del self.accounts[name]

        if self.active_account == name:
            self.active_account = next(iter(self.accounts), None)

        self.save()
        return True

    def get_active_account(self) -> Optional[Account]:
        """Get the currently active account."""
        if self.active_account and self.active_account in self.accounts:
            return self.accounts[self.active_account]
        return None

    def set_active_account(self, name: str) -> bool:
        """Set the active account."""
        if name not in self.accounts:
            return False
        self.active_account = name
        self.save()
        return True

    def save_query(self, name: str, query: str) -> None:
        """Save a query."""
        self.saved_queries[name] = SavedQuery(name=name, query=query)
        self.save()

    def delete_query(self, name: str) -> bool:
        """Delete a saved query."""
        if name not in self.saved_queries:
            return False
        del self.saved_queries[name]
        self.save()
        return True

    def get_query(self, name: str) -> Optional[SavedQuery]:
        """Get a saved query."""
        return self.saved_queries.get(name)
