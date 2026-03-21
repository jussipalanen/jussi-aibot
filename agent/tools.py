from vertexai.generative_models import FunctionDeclaration, Tool

search_properties = FunctionDeclaration(
    name="search_properties",
    description="Search for properties. Use when the user asks about available apartments, offices, or properties in a specific city or with specific criteria.",
    parameters={
        "type": "object",
        "properties": {
            "city":   {"type": "string", "description": "City to search in, e.g. Helsinki"},
            "type":   {"type": "string", "enum": ["apartment", "office"], "description": "Property type"},
            "status": {"type": "string", "enum": ["available", "unavailable", "maintenance"], "description": "Property status, default available"},
            "page":   {"type": "integer", "description": "Page number"},
            "limit":  {"type": "integer", "description": "Results per page"},
        },
    },
)

get_property = FunctionDeclaration(
    name="get_property",
    description="Get full details of a specific property by its ID.",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "Property ID"},
        },
        "required": ["id"],
    },
)

get_order_status = FunctionDeclaration(
    name="get_order_status",
    description="Get the status and details of a specific order by its ID. Use when the user asks about their booking or order.",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "Order ID"},
        },
        "required": ["id"],
    },
)

list_orders = FunctionDeclaration(
    name="list_orders",
    description="List orders, optionally filtered by user or status. Use when the user asks to see all their bookings.",
    parameters={
        "type": "object",
        "properties": {
            "userId":   {"type": "integer", "description": "Filter by user ID"},
            "status":   {"type": "string", "enum": ["pending", "approved", "declined", "cancelled"]},
            "page":     {"type": "integer"},
            "limit":    {"type": "integer"},
        },
    },
)

jussispace_tools = Tool(function_declarations=[
    search_properties,
    get_property,
    get_order_status,
    list_orders,
])
