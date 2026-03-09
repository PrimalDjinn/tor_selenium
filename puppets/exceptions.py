"""Custom exceptions for puppets."""


class PuppetsError(Exception):
    """Base exception for all puppets errors."""


class TorLaunchError(PuppetsError):
    """Raised when Tor fails to launch."""


class TorConnectionError(PuppetsError):
    """Raised when connection to Tor fails."""


class BrowserError(PuppetsError):
    """Raised when browser operations fail."""


class ChromeNotFoundError(BrowserError):
    """Raised when Chrome/Chromium is not found."""
