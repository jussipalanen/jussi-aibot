#!/usr/bin/env python3
"""
Generate a Postman Collection v2.1 from the FastAPI OpenAPI schema.

Usage:
    python scripts/generate_postman.py [--output postman_collection.json] [--base-url http://localhost:8080]
"""
import argparse
import json
import os
import sys
import uuid

# Must set env vars before importing the app (routes.py reads them at module load)
os.environ.setdefault("DEFAULT_PROVIDER", "puter_ai")
os.environ.setdefault("DISABLE_LOCAL_MODEL", "true")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


def _build_item(path: str, method: str, operation: dict, base_url: str) -> dict:
    name = operation.get("summary") or f"{method.upper()} {path}"
    description = operation.get("description", "")

    # Build URL
    clean_path = path.lstrip("/")
    url = {
        "raw": f"{base_url}/{clean_path}",
        "host": [base_url],
        "path": [p for p in clean_path.split("/") if p],
    }

    # Query params from GET operations
    query = []
    for param in operation.get("parameters", []):
        if param.get("in") == "query":
            query.append({
                "key": param["name"],
                "value": "",
                "description": param.get("description", ""),
                "disabled": not param.get("required", False),
            })
    if query:
        url["query"] = query

    # Request body
    body = None
    request_body = operation.get("requestBody", {})
    if request_body:
        content = request_body.get("content", {})
        if "multipart/form-data" in content:
            schema = content["multipart/form-data"].get("schema", {})
            form_data = []
            for field, props in schema.get("properties", {}).items():
                is_file = props.get("format") == "binary" or props.get("type") == "string" and "binary" in str(props)
                form_data.append({
                    "key": field,
                    "value": "" if not is_file else "",
                    "type": "file" if is_file else "text",
                    "description": props.get("description", ""),
                })
            body = {"mode": "formdata", "formdata": form_data}
        elif "application/json" in content:
            schema = content["application/json"].get("schema", {})
            body = {
                "mode": "raw",
                "raw": json.dumps(_example_from_schema(schema), indent=2),
                "options": {"raw": {"language": "json"}},
            }

    # Add Authorization header (disabled — fill in {{AI_SECRET_KEY}} and enable when testing)
    headers = [
        {
            "key": "Authorization",
            "value": "Bearer {{AI_SECRET_KEY}}",
            "type": "text",
            "disabled": True,
        }
    ]

    request: dict = {
        "method": method.upper(),
        "header": headers,
        "url": url,
    }
    if description:
        request["description"] = description
    if body:
        request["body"] = body

    return {"name": name, "request": request, "response": []}


def _example_from_schema(schema: dict) -> object:
    t = schema.get("type")
    if t == "object":
        return {k: _example_from_schema(v) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return [_example_from_schema(schema.get("items", {}))]
    if t == "integer":
        return schema.get("example", 0)
    if t == "number":
        return schema.get("example", 0.0)
    if t == "boolean":
        return schema.get("example", False)
    return schema.get("example", "")


def build_collection(base_url: str) -> dict:
    openapi = app.openapi()
    info = openapi.get("info", {})

    # Group items by tag
    folders: dict[str, list] = {}
    untagged: list = []

    for path, path_item in openapi.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            item = _build_item(path, method, operation, base_url)
            tags = operation.get("tags", [])
            if tags:
                for tag in tags:
                    folders.setdefault(tag, []).append(item)
            else:
                untagged.append(item)

    items = [
        {"name": tag, "item": folder_items}
        for tag, folder_items in folders.items()
    ]
    items.extend(untagged)

    return {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": info.get("title", "API Collection"),
            "description": info.get("description", ""),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [
            {"key": "base_url", "value": base_url, "type": "string"},
            {"key": "AI_SECRET_KEY", "value": "", "type": "secret"},
        ],
        "item": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Postman collection from FastAPI OpenAPI schema")
    parser.add_argument("--output", default="postman_collection.json", help="Output file path")
    parser.add_argument("--base-url", default="http://localhost:8080", help="Base URL for requests")
    args = parser.parse_args()

    collection = build_collection(args.base_url)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)

    print(f"Postman collection written to: {args.output}")
    print(f"  {len([i for folder in collection['item'] for i in (folder.get('item', [folder]) if 'item' in folder else [folder])])} requests across {len(collection['item'])} folder(s)")
    print(f"\nImport into Postman: File → Import → select {args.output}")


if __name__ == "__main__":
    main()
