"""
GraphQL Client Skill
GraphQL API client for queries and mutations.
"""

import json
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

METADATA = {
    "name": "graphql-client",
    "description": "Execute GraphQL queries and mutations against GraphQL APIs",
    "category": "web",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["graphql", "graphql query", "graphql mutation", "gql"],
    "dependencies": [],
    "tags": ["graphql", "api", "query", "mutation"]
}

SKILL_NAME = "graphql-client"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "web"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class GraphQLResponse:
    data: Any
    errors: List[Dict[str, Any]]
    extensions: Dict[str, Any]
    status_code: int
    elapsed: float


class GraphQLQueryBuilder:
    """Build GraphQL queries programmatically."""
    
    def __init__(self):
        self.query_type = 'query'
        self.operation_name: Optional[str] = None
        self.variables: Dict[str, Any] = {}
        self.variable_definitions: List[str] = []
        self.fields: List[str] = []
        self.arguments: Dict[str, Any] = {}
    
    def query(self, name: str = None) -> 'GraphQLQueryBuilder':
        """Set as query operation."""
        self.query_type = 'query'
        self.operation_name = name
        return self
    
    def mutation(self, name: str = None) -> 'GraphQLQueryBuilder':
        """Set as mutation operation."""
        self.query_type = 'mutation'
        self.operation_name = name
        return self
    
    def variable(self, name: str, type: str, default: Any = None) -> 'GraphQLQueryBuilder':
        """Add variable definition."""
        if default is not None:
            self.variable_definitions.append(f"${name}: {type} = {json.dumps(default)}")
        else:
            self.variable_definitions.append(f"${name}: {type}")
        return self
    
    def set_variables(self, variables: Dict[str, Any]) -> 'GraphQLQueryBuilder':
        """Set variable values."""
        self.variables = variables
        return self
    
    def argument(self, name: str, value: Any) -> 'GraphQLQueryBuilder':
        """Add argument to operation."""
        self.arguments[name] = value
        return self
    
    def field(self, name: str, alias: str = None, 
              arguments: Dict[str, Any] = None, 
              subfields: List[str] = None) -> 'GraphQLQueryBuilder':
        """Add field to selection set."""
        field_str = f"{alias}: {name}" if alias else name
        
        if arguments:
            args_str = ', '.join(f"{k}: {self._format_value(v)}" for k, v in arguments.items())
            field_str += f"({args_str})"
        
        if subfields:
            field_str += f" {{ {' '.join(subfields)} }}"
        
        self.fields.append(field_str)
        return self
    
    def _format_value(self, value: Any) -> str:
        """Format value for GraphQL."""
        if isinstance(value, str):
            if value.startswith('$'):
                return value
            return json.dumps(value)
        elif isinstance(value, bool):
            return 'true' if value else 'false'
        elif value is None:
            return 'null'
        elif isinstance(value, dict):
            return '{ ' + ', '.join(f"{k}: {self._format_value(v)}" for k, v in value.items()) + ' }'
        elif isinstance(value, list):
            return '[ ' + ', '.join(self._format_value(v) for v in value) + ' ]'
        else:
            return str(value)
    
    def build(self) -> str:
        """Build GraphQL query string."""
        parts = [self.query_type]
        
        # Add operation name and variables
        if self.operation_name or self.variable_definitions:
            name_part = self.operation_name or ''
            if self.variable_definitions:
                vars_part = '(' + ', '.join(self.variable_definitions) + ')'
                parts.append(f"{name_part}{vars_part}")
            else:
                parts.append(name_part)
        
        # Add arguments
        if self.arguments:
            args_str = ', '.join(f"{k}: {self._format_value(v)}" for k, v in self.arguments.items())
            parts.append(f"({args_str})")
        
        # Add fields
        if self.fields:
            parts.append('{ ' + ' '.join(self.fields) + ' }')
        
        return ' '.join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to request dictionary."""
        return {
            'query': self.build(),
            'variables': self.variables,
            'operationName': self.operation_name
        }


class GraphQLClient:
    """GraphQL API client."""
    
    def __init__(self, endpoint: str, headers: Dict[str, str] = None):
        self.endpoint = endpoint
        self.headers = headers or {}
        self.headers.setdefault('Content-Type', 'application/json')
        self.headers.setdefault('User-Agent', 'Sentience-GraphQL/1.0')
    
    def execute(self, query: str, variables: Dict = None, 
                operation_name: str = None) -> GraphQLResponse:
        """Execute a GraphQL query."""
        import time
        start = time.time()
        
        payload = {
            'query': query,
            'variables': variables or {}
        }
        
        if operation_name:
            payload['operationName'] = operation_name
        
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers=self.headers,
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw_body = response.read().decode('utf-8')
                result = json.loads(raw_body)
                
                elapsed = time.time() - start
                
                return GraphQLResponse(
                    data=result.get('data'),
                    errors=result.get('errors', []),
                    extensions=result.get('extensions', {}),
                    status_code=response.status,
                    elapsed=elapsed
                )
        
        except urllib.error.HTTPError as e:
            elapsed = time.time() - start
            raw_body = e.read().decode('utf-8')
            
            try:
                result = json.loads(raw_body)
            except json.JSONDecodeError:
                result = {'errors': [{'message': raw_body}]}
            
            return GraphQLResponse(
                data=result.get('data'),
                errors=result.get('errors', [{'message': str(e)}]),
                extensions=result.get('extensions', {}),
                status_code=e.code,
                elapsed=elapsed
            )
        
        except urllib.error.URLError as e:
            elapsed = time.time() - start
            return GraphQLResponse(
                data=None,
                errors=[{'message': str(e.reason)}],
                extensions={},
                status_code=0,
                elapsed=elapsed
            )
    
    def query(self, query: str, variables: Dict = None) -> GraphQLResponse:
        """Execute a GraphQL query."""
        return self.execute(query, variables)
    
    def mutation(self, mutation: str, variables: Dict = None) -> GraphQLResponse:
        """Execute a GraphQL mutation."""
        return self.execute(mutation, variables)
    
    def introspect(self) -> Dict[str, Any]:
        """Run introspection query to get schema."""
        introspection_query = '''
        query IntrospectionQuery {
            __schema {
                queryType { name }
                mutationType { name }
                subscriptionType { name }
                types {
                    ...FullType
                }
                directives {
                    name
                    description
                    locations
                    args {
                        ...InputValue
                    }
                }
            }
        }
        
        fragment FullType on __Type {
            kind
            name
            description
            fields(includeDeprecated: true) {
                name
                description
                args {
                    ...InputValue
                }
                type {
                    ...TypeRef
                }
                isDeprecated
                deprecationReason
            }
            inputFields {
                ...InputValue
            }
            interfaces {
                ...TypeRef
            }
            enumValues(includeDeprecated: true) {
                name
                description
                isDeprecated
                deprecationReason
            }
            possibleTypes {
                ...TypeRef
            }
        }
        
        fragment InputValue on __InputValue {
            name
            description
            type {
                ...TypeRef
            }
            defaultValue
        }
        
        fragment TypeRef on __Type {
            kind
            name
            ofType {
                kind
                name
                ofType {
                    kind
                    name
                    ofType {
                        kind
                        name
                        ofType {
                            kind
                            name
                            ofType {
                                kind
                                name
                                ofType {
                                    kind
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }
        '''
        
        response = self.execute(introspection_query)
        return response.data if response.data else {}
    
    def get_schema_summary(self) -> Dict[str, Any]:
        """Get a summary of the GraphQL schema."""
        schema = self.introspect()
        
        if not schema or '__schema' not in schema:
            return {"error": "Could not introspect schema"}
        
        schema_data = schema['__schema']
        
        # Extract types
        types = {}
        for t in schema_data.get('types', []):
            type_name = t.get('name', '')
            if not type_name.startswith('__'):
                types[type_name] = {
                    'kind': t.get('kind'),
                    'description': t.get('description'),
                    'fields': [f.get('name') for f in t.get('fields', [])]
                }
        
        return {
            'query_type': schema_data.get('queryType', {}).get('name'),
            'mutation_type': schema_data.get('mutationType', {}).get('name'),
            'subscription_type': schema_data.get('subscriptionType', {}).get('name'),
            'types': types,
            'type_count': len(types)
        }


def execute(
    endpoint: str,
    query: str = None,
    mutation: str = None,
    variables: Dict = None,
    headers: Dict = None,
    introspect: bool = False,
    schema_summary: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Execute GraphQL operations.
    
    Args:
        endpoint: GraphQL API endpoint URL
        query: GraphQL query string
        mutation: GraphQL mutation string
        variables: Query variables
        headers: Custom headers
        introspect: Run introspection query
        schema_summary: Get schema summary
    
    Returns:
        GraphQL response
    """
    client = GraphQLClient(endpoint, headers)
    
    if introspect:
        schema = client.introspect()
        return {
            "success": True,
            "schema": schema
        }
    
    if schema_summary:
        summary = client.get_schema_summary()
        return {
            "success": 'error' not in summary,
            "summary": summary
        }
    
    if mutation:
        response = client.mutation(mutation, variables)
        return {
            "success": len(response.errors) == 0,
            "data": response.data,
            "errors": response.errors,
            "status_code": response.status_code,
            "elapsed": response.elapsed
        }
    
    if query:
        response = client.query(query, variables)
        return {
            "success": len(response.errors) == 0,
            "data": response.data,
            "errors": response.errors,
            "status_code": response.status_code,
            "elapsed": response.elapsed
        }
    
    return {"success": False, "error": "query or mutation required"}
