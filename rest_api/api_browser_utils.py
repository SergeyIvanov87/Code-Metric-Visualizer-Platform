"""Shared path and metadata conventions for the REST API browser."""
import hashlib
import re
from urllib.parse import quote


def service_name(query, domain):
    relative = query.strip("/").removeprefix(domain.strip("/")).strip("/")
    parts = relative.split("/")
    return parts[0] if len(parts) > 1 else None


def service_page_url(service, domain):
    portal = "/" + domain.strip("/")
    return portal + "/_browse/services/" + quote(service, safe="") if service else portal


def query_page_url(query, method, domain):
    query_id = hashlib.sha256((method + " " + query).encode("utf-8")).hexdigest()
    return "/" + domain.strip("/") + "/_browse/queries/" + query_id


def request_fields(request_data, domain):
    query = request_data["Query"][request_data["Query"].find(domain):].strip("/")
    method = request_data["Method"]
    service = service_name(query, domain)
    return {"query": query, "method": method, "params": request_data["Params"],
            "content_type": request_data.get("Content-Type") or "text/plain",
            "service_name": service, "service_url": service_page_url(service, domain),
            "page_url": query_page_url(query, method, domain)}


def canonize(value):
    """Create a Python identifier; browser URLs retain their original spelling."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", value)
