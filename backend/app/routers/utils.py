"""Common route utilities and validators."""
from functools import wraps
from inspect import signature

from app.exceptions import NotFoundError
from app.models import portfolio as portfolio_model
from app.models import stock as stock_model


def require_portfolio_exists(func):
    """Decorator that validates portfolio_id exists before executing the route."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        portfolio_id = kwargs.get("portfolio_id") or (
            args[0] if args and "portfolio_id" in signature(func).parameters else None
        )
        if portfolio_id is not None:
            if portfolio_model.get_portfolio_by_id(portfolio_id) is None:
                raise NotFoundError(f"Portfolio {portfolio_id} not found")
        return func(*args, **kwargs)
    return wrapper


def require_stock_exists(func):
    """Decorator that validates stock_id exists before executing the route."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        stock_id = kwargs.get("stock_id") or (
            args[0] if args and "stock_id" in signature(func).parameters else None
        )
        if stock_id is not None:
            if stock_model.get_stock_by_id(stock_id) is None:
                raise NotFoundError(f"Stock {stock_id} not found")
        return func(*args, **kwargs)
    return wrapper


def require_user_exists(func):
    """Decorator that validates user_id exists before executing the route."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        from app.models import user as user_model
        user_id = kwargs.get("user_id") or (
            args[0] if args and "user_id" in signature(func).parameters else None
        )
        if user_id is not None:
            if user_model.get_user_by_id(user_id) is None:
                raise NotFoundError(f"User {user_id} not found")
        return func(*args, **kwargs)
    return wrapper
