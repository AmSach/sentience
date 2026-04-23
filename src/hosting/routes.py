"""
Sentience v3.0 - Route Management System
Dynamic route registration with middleware and error handling.
"""

import re
import json
import logging
import inspect
import asyncio
from typing import (
    Optional, Dict, Any, Callable, List, Union, Set,
    TypeVar, Generic, ParamSpec, Coroutine
)
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps, partial
from datetime import datetime
from pathlib import Path

from fastapi import (
    FastAPI, Request, Response, HTTPException,
    APIRouter, Depends, BackgroundTasks
)
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND


logger = logging.getLogger("sentience.routes")


P = ParamSpec("P")
T = TypeVar("T")


class HTTPMethod(str, Enum):
    """HTTP methods enum."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class RouteType(str, Enum):
    """Route types."""
    API = "api"
    PAGE = "page"
    STATIC = "static"
    WEBSOCKET = "websocket"


@dataclass
class RouteParameter:
    """Route parameter definition."""
    name: str
    type: type = str
    default: Any = None
    required: bool = True
    description: str = ""
    validation_pattern: Optional[str] = None
    
    def validate(self, value: Any) -> Any:
        """Validate parameter value."""
        if value is None:
            if self.required:
                raise ValueError(f"Parameter '{self.name}' is required")
            return self.default
        
        # Type conversion
        try:
            if self.type != str:
                value = self.type(value)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid type for '{self.name}': {e}")
        
        # Pattern validation
        if self.validation_pattern and isinstance(value, str):
            if not re.match(self.validation_pattern, value):
                raise ValueError(f"Invalid format for '{self.name}'")
        
        return value


@dataclass
class RouteDefinition:
    """Complete route definition."""
    path: str
    handler: Callable
    methods: List[HTTPMethod] = field(default_factory=lambda: [HTTPMethod.GET])
    route_type: RouteType = RouteType.API
    name: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    parameters: List[RouteParameter] = field(default_factory=list)
    middleware: List[Callable] = field(default_factory=list)
    response_model: Optional[type] = None
    status_code: int = 200
    deprecated: bool = False
    cache_ttl: Optional[int] = None
    rate_limit: Optional[int] = None
    require_auth: bool = False
    
    def __post_init__(self):
        if self.name is None:
            self.name = self.path.replace("/", "_").strip("_") or "root"


@dataclass
class RouteMatch:
    """Result of route matching."""
    route: RouteDefinition
    params: Dict[str, Any]
    path_params: Dict[str, Any]
    query_params: Dict[str, Any]


class RouteRegistry:
    """Central registry for all routes."""
    
    def __init__(self):
        self._routes: Dict[str, RouteDefinition] = {}
        self._pattern_routes: List[tuple] = []  # (pattern, route_def)
        self._middleware: List[Callable] = []
        self._error_handlers: Dict[int, Callable] = {}
        self._routers: Dict[str, APIRouter] = {}
    
    def register(
        self,
        path: str,
        handler: Callable,
        methods: List[HTTPMethod] = None,
        **kwargs
    ) -> RouteDefinition:
        """Register a new route."""
        methods = methods or [HTTPMethod.GET]
        
        route = RouteDefinition(
            path=path,
            handler=handler,
            methods=methods,
            **kwargs
        )
        
        # Check for dynamic parameters
        if "{" in path or ":" in path:
            # Convert to regex pattern
            pattern = self._path_to_pattern(path)
            self._pattern_routes.append((pattern, route))
        else:
            route_key = f"{'+'.join(m.value for m in methods)}:{path}"
            self._routes[route_key] = route
        
        logger.debug(f"Registered route: {methods} {path}")
        return route
    
    def _path_to_pattern(self, path: str) -> re.Pattern:
        """Convert path with parameters to regex pattern."""
        # Handle {param} and :param style parameters
        pattern_str = path
        
        # Convert {param} to named groups
        pattern_str = re.sub(
            r'\{(\w+)\}',
            r'(?P<\1>[^/]+)',
            pattern_str
        )
        
        # Convert :param to named groups
        pattern_str = re.sub(
            r':(\w+)',
            r'(?P<\1>[^/]+)',
            pattern_str
        )
        
        # Escape and anchor
        pattern_str = f"^{pattern_str}$"
        
        return re.compile(pattern_str)
    
    def match(self, path: str, method: HTTPMethod) -> Optional[RouteMatch]:
        """Match a path and method to a route."""
        # First check exact matches
        route_key = f"{method.value}:{path}"
        if route_key in self._routes:
            route = self._routes[route_key]
            return RouteMatch(
                route=route,
                params={},
                path_params={},
                query_params={}
            )
        
        # Check pattern routes
        for pattern, route in self._pattern_routes:
            if method not in route.methods:
                continue
            
            match = pattern.match(path)
            if match:
                return RouteMatch(
                    route=route,
                    params=match.groupdict(),
                    path_params=match.groupdict(),
                    query_params={}
                )
        
        return None
    
    def get_route(self, name: str) -> Optional[RouteDefinition]:
        """Get route by name."""
        for route in self._routes.values():
            if route.name == name:
                return route
        
        for _, route in self._pattern_routes:
            if route.name == name:
                return route
        
        return None
    
    def list_routes(self) -> List[RouteDefinition]:
        """List all registered routes."""
        routes = list(self._routes.values())
        routes.extend(route for _, route in self._pattern_routes)
        return routes
    
    def add_middleware(self, middleware: Callable):
        """Add global middleware."""
        self._middleware.append(middleware)
    
    def add_error_handler(self, status_code: int, handler: Callable):
        """Add error handler for status code."""
        self._error_handlers[status_code] = handler
    
    def create_router(self, prefix: str, tags: List[str] = None) -> APIRouter:
        """Create a new API router."""
        router = APIRouter(prefix=prefix, tags=tags or [])
        self._routers[prefix] = router
        return router


# Global registry
registry = RouteRegistry()


def route(
    path: str,
    methods: List[HTTPMethod] = None,
    **kwargs
):
    """Decorator to register a route."""
    def decorator(handler: Callable) -> Callable:
        registry.register(path, handler, methods=methods, **kwargs)
        return handler
    return decorator


def get(path: str, **kwargs):
    """GET route decorator."""
    return route(path, methods=[HTTPMethod.GET], **kwargs)


def post(path: str, **kwargs):
    """POST route decorator."""
    return route(path, methods=[HTTPMethod.POST], **kwargs)


def put(path: str, **kwargs):
    """PUT route decorator."""
    return route(path, methods=[HTTPMethod.PUT], **kwargs)


def patch(path: str, **kwargs):
    """PATCH route decorator."""
    return route(path, methods=[HTTPMethod.PATCH], **kwargs)


def delete(path: str, **kwargs):
    """DELETE route decorator."""
    return route(path, methods=[HTTPMethod.DELETE], **kwargs)


class Middleware:
    """Base middleware class."""
    
    async def __call__(self, request: Request, call_next: Callable):
        """Process request."""
        # Pre-processing
        response = await self.process_request(request)
        if response:
            return response
        
        # Call next handler
        response = await call_next(request)
        
        # Post-processing
        return await self.process_response(request, response)
    
    async def process_request(self, request: Request) -> Optional[Response]:
        """Process incoming request. Return response to short-circuit."""
        return None
    
    async def process_response(self, request: Request, response: Response) -> Response:
        """Process outgoing response."""
        return response


class AuthMiddleware(Middleware):
    """Authentication middleware."""
    
    def __init__(self, secret_key: str = None, header_name: str = "Authorization"):
        self.secret_key = secret_key or os.environ.get("AUTH_SECRET_KEY")
        self.header_name = header_name
    
    async def process_request(self, request: Request) -> Optional[Response]:
        """Validate authentication."""
        auth_header = request.headers.get(self.header_name)
        
        if not auth_header:
            return JSONResponse(
                {"error": "Missing authentication"},
                status_code=401
            )
        
        # Bearer token validation
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token != self.secret_key:
                return JSONResponse(
                    {"error": "Invalid token"},
                    status_code=403
                )
        
        return None


class RateLimitMiddleware(Middleware):
    """Rate limiting middleware."""
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: int = 10
    ):
        self.rpm = requests_per_minute
        self.burst = burst_size
        self._requests: Dict[str, List[float]] = {}
    
    async def process_request(self, request: Request) -> Optional[Response]:
        """Check rate limit."""
        import time
        
        client_id = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Get request history
        requests = self._requests.get(client_id, [])
        
        # Filter to last minute
        requests = [t for t in requests if now - t < 60]
        
        if len(requests) >= self.rpm:
            return JSONResponse(
                {"error": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60"}
            )
        
        # Update requests
        requests.append(now)
        self._requests[client_id] = requests
        
        return None


class CacheMiddleware(Middleware):
    """Response caching middleware."""
    
    def __init__(self, default_ttl: int = 300):
        self.default_ttl = default_ttl
        self._cache: Dict[str, tuple] = {}  # key -> (response, expiry)
    
    async def process_request(self, request: Request) -> Optional[Response]:
        """Check cache for cached response."""
        import time
        
        if request.method != "GET":
            return None
        
        cache_key = f"{request.url.path}?{request.url.query}"
        
        if cache_key in self._cache:
            response_data, expiry = self._cache[cache_key]
            
            if time.time() < expiry:
                logger.debug(f"Cache hit: {cache_key}")
                return JSONResponse(
                    response_data,
                    status_code=200,
                    headers={"X-Cache": "HIT"}
                )
            else:
                del self._cache[cache_key]
        
        return None
    
    async def process_response(self, request: Request, response: Response) -> Response:
        """Cache successful GET responses."""
        import time
        
        if request.method == "GET" and response.status_code == 200:
            if isinstance(response, JSONResponse):
                # Get response body
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                
                # Create new response with cached body
                cache_key = f"{request.url.path}?{request.url.query}"
                self._cache[cache_key] = (
                    json.loads(body),
                    time.time() + self.default_ttl
                )
                
                return JSONResponse(
                    json.loads(body),
                    status_code=200,
                    headers={**response.headers, "X-Cache": "MISS"}
                )
        
        return response


class CORSMiddleware(Middleware):
    """Custom CORS middleware with more control."""
    
    def __init__(
        self,
        allow_origins: List[str] = None,
        allow_methods: List[str] = None,
        allow_headers: List[str] = None,
        allow_credentials: bool = True,
        max_age: int = 600
    ):
        self.origins = set(allow_origins or ["*"])
        self.methods = allow_methods or ["*"]
        self.headers = allow_headers or ["*"]
        self.credentials = allow_credentials
        self.max_age = max_age
    
    async def process_request(self, request: Request) -> Optional[Response]:
        """Handle CORS preflight."""
        if request.method == "OPTIONS":
            origin = request.headers.get("origin", "*")
            
            if "*" in self.origins or origin in self.origins:
                headers = {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": ", ".join(self.methods),
                    "Access-Control-Allow-Headers": ", ".join(self.headers),
                    "Access-Control-Max-Age": str(self.max_age)
                }
                
                if self.credentials:
                    headers["Access-Control-Allow-Credentials"] = "true"
                
                return PlainTextResponse("", status_code=204, headers=headers)
        
        return None
    
    async def process_response(self, request: Request, response: Response) -> Response:
        """Add CORS headers to response."""
        origin = request.headers.get("origin", "*")
        
        if "*" in self.origins or origin in self.origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            
            if self.credentials:
                response.headers["Access-Control-Allow-Credentials"] = "true"
        
        return response


class ErrorHandler:
    """Centralized error handling."""
    
    def __init__(self, app: FastAPI = None):
        self.app = app
        self._handlers: Dict[int, Callable] = {}
        self._exception_handlers: Dict[type, Callable] = {}
    
    def handle(self, status_code: int):
        """Decorator to register error handler."""
        def decorator(handler: Callable):
            self._handlers[status_code] = handler
            if self.app:
                self.app.add_exception_handler(status_code, handler)
            return handler
        return decorator
    
    def exception(self, exception_type: type):
        """Decorator to register exception handler."""
        def decorator(handler: Callable):
            self._exception_handlers[exception_type] = handler
            if self.app:
                self.app.add_exception_handler(exception_type, handler)
            return handler
        return decorator
    
    def create_error_response(
        self,
        status_code: int,
        message: str,
        details: Dict = None,
        request_id: str = None
    ) -> JSONResponse:
        """Create standardized error response."""
        error = {
            "error": {
                "code": status_code,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        if details:
            error["error"]["details"] = details
        
        if request_id:
            error["error"]["request_id"] = request_id
        
        return JSONResponse(error, status_code=status_code)


def param(
    name: str,
    type: type = str,
    default: Any = None,
    required: bool = True,
    description: str = "",
    pattern: str = None
) -> RouteParameter:
    """Create a route parameter definition."""
    return RouteParameter(
        name=name,
        type=type,
        default=default,
        required=required,
        description=description,
        validation_pattern=pattern
    )


def validate_params(*params: RouteParameter):
    """Decorator to validate route parameters."""
    def decorator(handler: Callable):
        @wraps(handler)
        async def wrapper(*args, **kwargs):
            # Merge all kwargs for validation
            all_params = kwargs
            
            for param in params:
                value = all_params.get(param.name)
                try:
                    validated = param.validate(value)
                    kwargs[param.name] = validated
                except ValueError as e:
                    raise HTTPException(
                        status_code=HTTP_400_BAD_REQUEST,
                        detail=str(e)
                    )
            
            return await handler(*args, **kwargs)
        
        return wrapper
    return decorator


class DynamicRouter:
    """Dynamic router that loads routes from configuration."""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path
        self._loaded_routes: List[RouteDefinition] = []
    
    def load_from_file(self, path: str) -> List[RouteDefinition]:
        """Load routes from JSON/YAML file."""
        path = Path(path)
        
        if not path.exists():
            raise FileNotFoundError(f"Route config not found: {path}")
        
        if path.suffix == ".json":
            with open(path) as f:
                config = json.load(f)
        elif path.suffix in [".yaml", ".yml"]:
            import yaml
            with open(path) as f:
                config = yaml.safe_load(f)
        else:
            raise ValueError(f"Unsupported config format: {path.suffix}")
        
        routes = []
        for route_config in config.get("routes", []):
            route = RouteDefinition(
                path=route_config["path"],
                handler=self._get_handler(route_config.get("handler")),
                methods=[HTTPMethod(m) for m in route_config.get("methods", ["GET"])],
                name=route_config.get("name"),
                description=route_config.get("description"),
                tags=route_config.get("tags", [])
            )
            routes.append(route)
        
        self._loaded_routes = routes
        return routes
    
    def _get_handler(self, handler_path: str) -> Callable:
        """Import and return handler function."""
        if not handler_path:
            return lambda request: {"status": "ok"}
        
        module_path, func_name = handler_path.rsplit(".", 1)
        
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    
    def apply_to_app(self, app: FastAPI):
        """Apply loaded routes to FastAPI app."""
        for route in self._loaded_routes:
            for method in route.methods:
                app.add_api_route(
                    route.path,
                    route.handler,
                    methods=[method.value],
                    name=route.name,
                    tags=route.tags
                )


def setup_routes(app: FastAPI, routes: List[RouteDefinition] = None):
    """Setup routes on FastAPI application."""
    routes = routes or registry.list_routes()
    
    for route in routes:
        for method in route.methods:
            app.add_api_route(
                route.path,
                route.handler,
                methods=[method.value],
                name=route.name,
                description=route.description,
                tags=route.tags,
                deprecated=route.deprecated
            )
    
    return app


# Example route definitions
@get("/")
async def root():
    """Root endpoint."""
    return {"message": "Sentience v3.0 Hosting"}


@get("/routes")
async def list_routes():
    """List all registered routes."""
    return {
        "routes": [
            {
                "path": r.path,
                "methods": [m.value for m in r.methods],
                "name": r.name
            }
            for r in registry.list_routes()
        ]
    }


@get("/users/{user_id}")
@param("user_id", type=int, required=True)
async def get_user(user_id: int):
    """Get user by ID."""
    return {"user_id": user_id, "name": f"User {user_id}"}


@post("/users")
async def create_user(request: Request):
    """Create new user."""
    data = await request.json()
    return {"created": True, "user": data}
