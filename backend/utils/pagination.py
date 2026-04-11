from typing import Callable, Any

def paginate(query, skip: int, limit: int, serializer: Callable[[Any], dict]) -> dict:
    """
    Generic paginator for SQLAlchemy queries.
    Returns: { items, total, skip, limit }
    """
    total = query.count()
    rows  = query.offset(skip).limit(limit).all()
    return {
        "items": [serializer(r) for r in rows],
        "total": total,
        "skip":  skip,
        "limit": limit,
    }
