"""Platform exception hierarchy."""


class QuantPlatformError(Exception):
    """Base class for errors raised by the platform."""


class ConfigurationError(QuantPlatformError):
    """Raised when application configuration is invalid."""


class PluginError(QuantPlatformError):
    """Raised when a plugin cannot be registered or resolved."""


class DataError(QuantPlatformError):
    """Base class for market-data errors."""


class DataUnavailableError(DataError):
    """Raised when no configured provider can supply requested data."""


class DataCapabilityNotSupported(DataError):
    """Raised when a provider does not implement a requested dataset."""


class DataQualityError(DataError):
    """Raised when data does not satisfy its contract."""


class AccountError(QuantPlatformError):
    """Raised when a fill would make account state invalid."""
