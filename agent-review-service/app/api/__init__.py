"""FastAPI 路由层。"""

from .admin_router import router as admin_router
from .review_router import router as review_router

__all__ = ["review_router", "admin_router"]
