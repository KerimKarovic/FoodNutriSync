
import logging
import sys
import os
from datetime import datetime
from typing import Any, Dict
import json

class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log structure
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_entry.update(getattr(record, 'extra_data', {}))
            
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry, ensure_ascii=False)

def setup_logging():
    """Configure application logging"""
    
    # Create logs directory if it doesn't exist
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create formatters
    structured_formatter = StructuredFormatter()
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler (human-readable)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    
    # File handler (structured JSON)
    log_file_path = os.path.join(logs_dir, 'app.log')
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setFormatter(structured_formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Configure specific loggers
    app_logger = logging.getLogger("foodnutrisync")
    app_logger.setLevel(logging.DEBUG)
    
    # Reduce noise from external libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    return app_logger

class AppLogger:
    """Application-specific logger with structured logging methods"""
    
    def __init__(self):
        self.logger = logging.getLogger("foodnutrisync")
    
    def error(self, message: str) -> None:
        """Standard error logging"""
        self.logger.error(message)
    
    def info(self, message: str) -> None:
        """Standard info logging"""
        self.logger.info(message)
    
    def log_upload_start(self, filename: str, file_size: int, user_ip: str | None = None):
        """Log file upload initiation"""
        self.logger.info(
            "File upload started",
            extra={
                'extra_data': {
                    'event_type': 'upload_start',
                    'filename': filename,
                    'file_size_bytes': file_size,
                    'user_ip': user_ip
                }
            }
        )
    
    def log_upload_success(self, filename: str, added: int, updated: int, failed: int, duration_ms: float):
        """Log successful file upload"""
        self.logger.info(
            f"File upload completed successfully: {added} added, {updated} updated, {failed} failed",
            extra={
                'extra_data': {
                    'event_type': 'upload_success',
                    'filename': filename,
                    'records_added': added,
                    'records_updated': updated,
                    'records_failed': failed,
                    'duration_ms': duration_ms,
                    'total_processed': added + updated + failed
                }
            }
        )
    
    def log_upload_error(self, filename: str, error: str, duration_ms: float):
        """Log failed file upload"""
        self.logger.error(
            f"File upload failed: {error}",
            extra={
                'extra_data': {
                    'event_type': 'upload_error',
                    'filename': filename,
                    'error_message': error,
                    'duration_ms': duration_ms
                }
            }
        )
    
    def log_api_query(self, endpoint: str, params: Dict[str, Any], result_count: int, duration_ms: float, user_ip: str | None = None):
        """Log API query"""
        self.logger.info(
            f"API query: {endpoint}",
            extra={
                'extra_data': {
                    'event_type': 'api_query',
                    'endpoint': endpoint,
                    'parameters': params,
                    'result_count': result_count,
                    'duration_ms': duration_ms,
                    'user_ip': user_ip
                }
            }
        )
    
    def log_database_operation(self, operation: str, table: str, affected_rows: int, duration_ms: float):
        """Log database operations"""
        self.logger.debug(
            f"Database {operation}: {affected_rows} rows affected",
            extra={
                'extra_data': {
                    'event_type': 'database_operation',
                    'operation': operation,
                    'table': table,
                    'affected_rows': affected_rows,
                    'duration_ms': duration_ms
                }
            }
        )
    
    def log_validation_error(self, filename: str, row_number: int, error: str):
        """Log data validation errors"""
        self.logger.warning(
            f"Validation error in {filename} row {row_number}: {error}",
            extra={
                'extra_data': {
                    'event_type': 'validation_error',
                    'filename': filename,
                    'row_number': row_number,
                    'error_message': error
                }
            }
        )

# Global logger instance
app_logger = AppLogger()

