"""Exceptions for the Junos NETCONF integration."""


class JunosNetconfError(Exception):
    """Base exception for Junos NETCONF errors."""


class JunosNetconfAuthError(JunosNetconfError):
    """Raised when NETCONF authentication fails."""


class JunosNetconfConnectionError(JunosNetconfError):
    """Raised when NETCONF connection, timeout, or RPC handling fails."""
