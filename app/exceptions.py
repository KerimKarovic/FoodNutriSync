"""Custom exceptions for the application"""

class FoodNutriSyncError(Exception):
    """Base exception for all application errors"""
    pass


class BLSError(FoodNutriSyncError):
    """Base exception for BLS-related errors"""
    pass


class BLSNotFoundError(BLSError):
    """Raised when BLS number is not found"""
    pass


class BLSValidationError(BLSError):
    """Raised when BLS data validation fails"""
    pass


class FileUploadError(FoodNutriSyncError):
    """Raised when file upload fails"""
    pass


class DatabaseError(FoodNutriSyncError):
    """Raised when database operations fail"""
    pass