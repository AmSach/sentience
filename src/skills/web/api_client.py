"""
API Client Skill
REST API client for making HTTP requests.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from urllib.parse import urlencode
from base64 import b64encode

METADATA = {
    "name": "api-client",
    "description": "Make HTTP requests to REST APIs with authentication support",
    "category": "web",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["api call", "http request", "rest api", "fetch api"],
    "dependencies": [],
    "tags": ["api", "http", "rest", "client"]
}

SKILL_NAME = "api-client"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "web"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class APIResponse:
    status_code: int
    headers: Dict[str, str]
    body: Any
    url: str
    elapsed: float


class APIClient:
    """REST API client with authentication support."""
    
    def __init__(self, base_url: str = None, default_headers: Dict[str, str] = None):
        self.base_url = base_url or ""
        self.default_headers = default_headers or {
            'User-Agent': 'Sentience-APIClient/1.0',
            'Accept': 'application/json'
        }
        self.auth_token = None
        self.auth_type = None
        self.auth_header = None
    
    def set_bearer_auth(self, token: str):
        """Set Bearer token authentication."""
        self.auth_token = token
        self.auth_type = 'bearer'
        self.auth_header = f'Bearer {token}'
    
    def set_basic_auth(self, username: str, password: str):
        """Set Basic authentication."""
        credentials = f'{username}:{password}'
        self.auth_token = b64encode(credentials.encode()).decode()
        self.auth_type = 'basic'
        self.auth_header = f'Basic {self.auth_token}'
    
    def set_api_key(self, key: str, header_name: str = 'X-API-Key'):
        """Set API key authentication."""
        self.auth_token = key
        self.auth_type = 'api_key'
        self.auth_header = key
        self.auth_header_name = header_name
    
    def set_oauth2(self, access_token: str):
        """Set OAuth2 access token."""
        self.set_bearer_auth(access_token)
    
    def _build_url(self, endpoint: str, params: Dict = None) -> str:
        """Build full URL with query parameters."""
        url = f"{self.base_url}{endpoint}" if self.base_url else endpoint
        
        if params:
            query_string = urlencode(params)
            url = f"{url}?{query_string}" if '?' in url else f"{url}?{query_string}"
        
        return url
    
    def _get_headers(self, custom_headers: Dict = None, content_type: str = None) -> Dict[str, str]:
        """Build headers for request."""
        headers = dict(self.default_headers)
        
        if self.auth_header:
            if self.auth_type == 'api_key':
                headers[self.auth_header_name] = self.auth_header
            else:
                headers['Authorization'] = self.auth_header
        
        if content_type:
            headers['Content-Type'] = content_type
        
        if custom_headers:
            headers.update(custom_headers)
        
        return headers
    
    def _make_request(self, method: str, url: str, headers: Dict, 
                      data: Any = None, json_data: Any = None, timeout: int = 30) -> APIResponse:
        """Make HTTP request."""
        import time
        start = time.time()
        
        # Prepare body
        body = None
        if json_data is not None:
            body = json.dumps(json_data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        elif data is not None:
            if isinstance(data, dict):
                body = urlencode(data).encode('utf-8')
            elif isinstance(data, str):
                body = data.encode('utf-8')
        
        # Create request
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_headers = dict(response.headers)
                
                # Parse response body
                raw_body = response.read().decode('utf-8', errors='ignore')
                
                content_type = response_headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    try:
                        response_body = json.loads(raw_body)
                    except json.JSONDecodeError:
                        response_body = raw_body
                else:
                    response_body = raw_body
                
                elapsed = time.time() - start
                
                return APIResponse(
                    status_code=response.status,
                    headers=response_headers,
                    body=response_body,
                    url=url,
                    elapsed=elapsed
                )
        
        except urllib.error.HTTPError as e:
            elapsed = time.time() - start
            
            # Try to parse error response
            try:
                raw_body = e.read().decode('utf-8')
                try:
                    response_body = json.loads(raw_body)
                except json.JSONDecodeError:
                    response_body = raw_body
            except:
                response_body = str(e)
            
            return APIResponse(
                status_code=e.code,
                headers=dict(e.headers),
                body=response_body,
                url=url,
                elapsed=elapsed
            )
        
        except urllib.error.URLError as e:
            elapsed = time.time() - start
            return APIResponse(
                status_code=0,
                headers={},
                body={"error": str(e.reason)},
                url=url,
                elapsed=elapsed
            )
    
    def request(self, method: str, endpoint: str, params: Dict = None,
                data: Any = None, json_data: Any = None, 
                headers: Dict = None, timeout: int = 30) -> APIResponse:
        """Make HTTP request."""
        url = self._build_url(endpoint, params)
        request_headers = self._get_headers(headers)
        return self._make_request(method, url, request_headers, data, json_data, timeout)
    
    def get(self, endpoint: str, params: Dict = None, headers: Dict = None, 
            timeout: int = 30) -> APIResponse:
        """GET request."""
        return self.request('GET', endpoint, params=params, headers=headers, timeout=timeout)
    
    def post(self, endpoint: str, data: Any = None, json_data: Any = None,
             params: Dict = None, headers: Dict = None, timeout: int = 30) -> APIResponse:
        """POST request."""
        return self.request('POST', endpoint, params=params, data=data, 
                           json_data=json_data, headers=headers, timeout=timeout)
    
    def put(self, endpoint: str, data: Any = None, json_data: Any = None,
            params: Dict = None, headers: Dict = None, timeout: int = 30) -> APIResponse:
        """PUT request."""
        return self.request('PUT', endpoint, params=params, data=data,
                           json_data=json_data, headers=headers, timeout=timeout)
    
    def patch(self, endpoint: str, data: Any = None, json_data: Any = None,
              params: Dict = None, headers: Dict = None, timeout: int = 30) -> APIResponse:
        """PATCH request."""
        return self.request('PATCH', endpoint, params=params, data=data,
                           json_data=json_data, headers=headers, timeout=timeout)
    
    def delete(self, endpoint: str, params: Dict = None, headers: Dict = None,
               timeout: int = 30) -> APIResponse:
        """DELETE request."""
        return self.request('DELETE', endpoint, params=params, headers=headers, timeout=timeout)
    
    def head(self, endpoint: str, params: Dict = None, headers: Dict = None,
             timeout: int = 30) -> APIResponse:
        """HEAD request."""
        return self.request('HEAD', endpoint, params=params, headers=headers, timeout=timeout)
    
    def options(self, endpoint: str, params: Dict = None, headers: Dict = None,
                timeout: int = 30) -> APIResponse:
        """OPTIONS request."""
        return self.request('OPTIONS', endpoint, params=params, headers=headers, timeout=timeout)


class APIResponseDecoder:
    """Decode and transform API responses."""
    
    @staticmethod
    def to_dict(response: APIResponse) -> Dict[str, Any]:
        """Convert response to dictionary."""
        return {
            'status_code': response.status_code,
            'headers': response.headers,
            'body': response.body,
            'url': response.url,
            'elapsed': response.elapsed
        }
    
    @staticmethod
    def is_success(response: APIResponse) -> bool:
        """Check if response indicates success."""
        return 200 <= response.status_code < 300
    
    @staticmethod
    def is_client_error(response: APIResponse) -> bool:
        """Check if response indicates client error."""
        return 400 <= response.status_code < 500
    
    @staticmethod
    def is_server_error(response: APIResponse) -> bool:
        """Check if response indicates server error."""
        return response.status_code >= 500
    
    @staticmethod
    def get_pagination(response: APIResponse, 
                       next_key: str = 'next', 
                       prev_key: str = 'previous') -> Dict[str, Any]:
        """Extract pagination info from response."""
        body = response.body if isinstance(response.body, dict) else {}
        
        return {
            'next': body.get(next_key),
            'previous': body.get(prev_key),
            'total': body.get('total', body.get('count')),
            'page': body.get('page'),
            'per_page': body.get('per_page', body.get('limit'))
        }


def execute(
    url: str = None,
    endpoint: str = None,
    method: str = "GET",
    base_url: str = None,
    params: Dict = None,
    data: Any = None,
    json_data: Any = None,
    headers: Dict = None,
    auth_type: str = None,
    auth_token: str = None,
    username: str = None,
    password: str = None,
    api_key: str = None,
    timeout: int = 30,
    **kwargs
) -> Dict[str, Any]:
    """
    Make HTTP requests to REST APIs.
    
    Args:
        url: Full URL (overrides base_url + endpoint)
        endpoint: API endpoint
        method: HTTP method
        base_url: Base URL for API
        params: Query parameters
        data: Form data
        json_data: JSON body
        headers: Custom headers
        auth_type: Authentication type (bearer/basic/api_key/oauth2)
        auth_token: Auth token
        username: Username for basic auth
        password: Password for basic auth
        api_key: API key
        timeout: Request timeout
    
    Returns:
        API response
    """
    # Determine URL
    if url:
        base_url = ""
        endpoint = url
    
    client = APIClient(base_url, headers)
    
    # Set authentication
    if auth_type == 'bearer' or auth_type == 'oauth2':
        client.set_bearer_auth(auth_token)
    elif auth_type == 'basic' and username and password:
        client.set_basic_auth(username, password)
    elif auth_type == 'api_key' or api_key:
        client.set_api_key(api_key or auth_token)
    
    # Make request
    method = method.upper()
    
    if method == 'GET':
        response = client.get(endpoint, params, headers, timeout)
    elif method == 'POST':
        response = client.post(endpoint, data, json_data, params, headers, timeout)
    elif method == 'PUT':
        response = client.put(endpoint, data, json_data, params, headers, timeout)
    elif method == 'PATCH':
        response = client.patch(endpoint, data, json_data, params, headers, timeout)
    elif method == 'DELETE':
        response = client.delete(endpoint, params, headers, timeout)
    elif method == 'HEAD':
        response = client.head(endpoint, params, headers, timeout)
    elif method == 'OPTIONS':
        response = client.options(endpoint, params, headers, timeout)
    else:
        return {"success": False, "error": f"Unknown method: {method}"}
    
    return {
        "success": APIResponseDecoder.is_success(response),
        "status_code": response.status_code,
        "headers": response.headers,
        "body": response.body,
        "url": response.url,
        "elapsed": response.elapsed
    }
