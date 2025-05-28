#!/usr/bin/env python3

"""
Logging Configuration for SPX Straddle Calculator
Supports both local logging and Loki integration for centralized log management
"""

import logging
import logging.handlers
import os
import sys
from typing import Optional
import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def setup_loki_handler() -> Optional[logging.Handler]:
    """
    Set up Loki logging handler if configured
    
    Returns:
        Loki handler if configured, None otherwise
    """
    loki_url = os.getenv("LOKI_URL")
    if not loki_url:
        return None
    
    try:
        from logging_loki import LokiHandler
        
        # Create Loki handler with custom labels
        loki_handler = LokiHandler(
            url=f"{loki_url}/loki/api/v1/push",
            tags={
                "application": "spx-straddle-calculator",
                "environment": os.getenv("ENVIRONMENT", "production"),
                "service": "spx-calculator",
                "version": "1.0.0"
            },
            version="1"
        )
        
        # Set formatter for Loki
        loki_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        loki_handler.setFormatter(loki_formatter)
        
        return loki_handler
        
    except ImportError:
        print("Warning: python-logging-loki not installed. Loki logging disabled.")
        return None
    except Exception as e:
        print(f"Warning: Failed to setup Loki handler: {e}")
        return None

def setup_prometheus_metrics():
    """
    Set up Prometheus metrics for monitoring
    """
    try:
        from prometheus_client import Counter, Histogram, Gauge, start_http_server
        
        # Define metrics
        metrics = {
            'calculations_total': Counter(
                'spx_calculations_total',
                'Total number of SPX straddle calculations',
                ['status']  # success, failure
            ),
            'calculation_duration': Histogram(
                'spx_calculation_duration_seconds',
                'Time spent calculating SPX straddle costs',
                buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
            ),
            'straddle_cost': Gauge(
                'spx_straddle_cost_dollars',
                'Current SPX straddle cost in dollars'
            ),
            'spx_price': Gauge(
                'spx_price_dollars',
                'Current SPX index price'
            ),
            'discord_notifications': Counter(
                'discord_notifications_total',
                'Total Discord notifications sent',
                ['status']  # success, failure
            ),
            'api_requests': Counter(
                'api_requests_total',
                'Total API requests',
                ['method', 'endpoint', 'status']
            ),
            'redis_operations': Counter(
                'redis_operations_total',
                'Total Redis operations',
                ['operation', 'status']  # get, set, delete / success, failure
            )
        }
        
        # Start Prometheus metrics server if enabled
        metrics_port = int(os.getenv("PROMETHEUS_METRICS_PORT", "9090"))
        if os.getenv("PROMETHEUS_METRICS_ENABLED", "false").lower() == "true":
            try:
                start_http_server(metrics_port)
                print(f"Prometheus metrics server started on port {metrics_port}")
            except Exception as e:
                print(f"Warning: Failed to start Prometheus metrics server: {e}")
        
        return metrics
        
    except ImportError:
        print("Warning: prometheus-client not installed. Metrics disabled.")
        return {}
    except Exception as e:
        print(f"Warning: Failed to setup Prometheus metrics: {e}")
        return {}

def configure_logging():
    """
    Configure comprehensive logging for the SPX Straddle Calculator
    
    Supports:
    - Console logging
    - File logging with rotation
    - Loki integration (if configured)
    - Structured logging with context
    """
    
    # Get configuration from environment
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = os.getenv("LOG_FILE", "logs/spx_calculator.log")
    loki_enabled = os.getenv("LOKI_ENABLED", "false").lower() == "true"
    
    # Create logs directory if it doesn't exist
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(getattr(logging, log_level))
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(getattr(logging, log_level))
    root_logger.addHandler(file_handler)
    
    # Loki handler (if configured)
    if loki_enabled:
        loki_handler = setup_loki_handler()
        if loki_handler:
            loki_handler.setLevel(getattr(logging, log_level))
            root_logger.addHandler(loki_handler)
            print("Loki logging enabled")
        else:
            print("Loki logging requested but failed to initialize")
    
    # Configure structlog for better structured logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Set up specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    print(f"Logging configured - Level: {log_level}, File: {log_file}, Loki: {loki_enabled}")

def get_logger(name: str):
    """
    Get a configured logger instance
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Configured logger instance
    """
    return structlog.get_logger(name)

# Global metrics instance
METRICS = setup_prometheus_metrics()

def get_metrics():
    """Get the global metrics instance"""
    return METRICS

# Initialize logging when module is imported
if __name__ != "__main__":
    configure_logging() 