"""Rate limiting utilities for API calls with exponential backoff and jitter."""

import asyncio
import logging
import random
import time
from typing import Any, Callable, TypeVar

import structlog
from tenacity import (
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_random_exponential,
)

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class RateLimiter:
    """Rate limiter with exponential backoff and jitter for API calls."""
    
    def __init__(self, max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 60.0):
        """Initialize rate limiter.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
            max_delay: Maximum delay in seconds
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.last_request_time = 0
        self.min_request_interval = 0.1  # Minimum 100ms between requests
    
    def wait_if_needed(self):
        """Wait if minimum interval between requests hasn't passed."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            logger.debug("Rate limiting: waiting", sleep_time=sleep_time)
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(multiplier=1, min=1, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    async def execute_with_backoff(self, func: Callable[..., Any], *args, **kwargs) -> T:
        """Execute function with exponential backoff and jitter.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Result of function execution
            
        Raises:
            Last exception if all retries are exhausted
        """
        self.wait_if_needed()
        
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as e:
            logger.warning("Rate limit or API error", error=str(e), attempt=func.__name__)
            raise


def create_retry_decorator(max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 60.0):
    """Create a retry decorator with exponential backoff and jitter.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        
    Returns:
        Decorator function
    """
    return retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=base_delay, max=max_delay) + wait_random_exponential(multiplier=0.1, min=0, max=1),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )


def get_token_delay_function():
    """Get a function to calculate delay based on token usage."""
    
    def calculate_delay(tokens_used: int, limit: int = 6000) -> float:
        """Calculate delay based on token usage.
        
        Args:
            tokens_used: Number of tokens used in request
            limit: Token limit per minute
            
        Returns:
            Delay in seconds before next request
        """
        if tokens_used < limit * 0.5:  # Under 50% of limit
            return 0.1
        elif tokens_used < limit * 0.8:  # Under 80% of limit
            return 1.0
        else:  # Over 80% of limit
            return 2.0 + random.uniform(0, 1)  # Add jitter
    
    return calculate_delay
