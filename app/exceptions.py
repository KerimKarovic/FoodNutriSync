"""Custom exceptions for the BLS application."""


class BLSNotFoundError(Exception):
    """Raised when a BLS food item is not found."""
    pass


class BLSValidationError(Exception):
    """Raised when BLS data validation fails."""
    pass


class FileUploadError(Exception):
    """Raised when file upload processing fails."""
    pass