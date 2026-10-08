# Access Control

How the API decides who may call it. The code is in `aibot/security.py`; the tests are in `tests/test_security.py`.

## Clients

A **client** is one caller of the API, such as a backend or a website. Each client has:

| Field | Meaning |
|---|---|
| `key` / `key_sha256` | API key for server-to-server calls, sent as `Authorization: Bearer <key>` |
| `origins` | Browser origins the client may call from |
| `agents`, `rubrics` | What it may use (`*` = everything) |
| `rate_limit` | Its own limit, e.g. `50/day` |

Clients come from `config/clients.yaml` (or `CLIENTS_FILE`). Without that file, `AI_SECRET_KEY` and `ALLOWED_ORIGINS` define a single client. With neither, the API is open — for local development only.

## How a request is matched

| Request | Result |
|---|---|
| Bearer key matches a client | ✅ That client. If the client lists origins and the request has an `Origin` header, it must be one of them, otherwise `403`. |
| No key, `Origin` belongs to a client without a key | ✅ That browser client |
| No key, `Origin` belongs to a client with a key | ❌ `401` — the key is required |
| No key and no known origin | ❌ `401` (no `Origin`) or `403` (unknown `Origin`) |
| Invalid key or malformed `Authorization` header | ❌ `401` |

Details:

- Keys are compared as SHA-256 hashes with `hmac.compare_digest`, so the config can hold hashes instead of keys.
- Origins must match exactly after removing a trailing slash: scheme, host and port. Prefixes (`https://app.test.evil.test`), other ports and other schemes are rejected.
- A client can only use the agents and rubrics it lists; others answer `404`, as if they did not exist.

## What origins do and don't protect

Browsers set the `Origin` header themselves, and JavaScript cannot change it, so a browser client cannot be used from another website. Scripts (curl, servers) can send any `Origin`, so a browser-only client is effectively public. Use browser-only clients for low-risk agents with tight rate limits, and keep API keys on servers — never in browser JavaScript.

## CORS

Browsers may call from any origin listed for any client; other origins get no `Access-Control-Allow-Origin` header and the browser blocks the response. Without any origins configured, CORS allows all origins (keys are still required when configured).

## Rate limits

Each request to chat or review counts against the client's limit, per IP address, separately for chat and review. Exceeding it returns `429` with `Retry-After`. Limits are kept in memory per instance.

Behind a proxy the IP is the proxy's unless `FORWARDED_IP_DEPTH` is set. It reads `X-Forwarded-For` from the right, because entries on the left can be supplied by the caller.

## Agent tools

The model chooses only argument values for tools. Hosts, paths and methods come from the agent config, path values are URL-encoded, and arguments not declared in the tool's JSON Schema are dropped. Backend credentials stay in environment variables and are never shown to the model.

## Testing

```bash
pytest tests/test_security.py tests/test_origin_security.py -v

# Against a running server
./tests/verify_origin_security.sh
./tests/test_origin_access.sh
```
