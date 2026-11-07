"""Shared path and metadata conventions for the REST API browser."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote


def service_name(query, domain):
    relative = query.strip("/").removeprefix(domain.strip("/")).strip("/")
    parts = relative.split("/")
    return parts[0] if relative else None


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
    query_id = hashlib.sha256((method + " " + query).encode("utf-8")).hexdigest()
    return {"query_id": query_id, "query": query, "method": method, "params": request_data["Params"],
            "content_type": request_data.get("Content-Type") or "text/plain",
            "service_name": service, "service_url": service_page_url(service, domain),
            "page_url": query_page_url(query, method, domain)}


def response_presentation(request_data):
    """Use the MIME metadata recovered from the result FIFO's extension."""
    from api_schema_utils import file_extension_from_content_type_or_default

    extension = file_extension_from_content_type_or_default(request_data, "txt")
    if extension in {"json", "xml", "html"}:
        kind = extension
    elif extension in {"apng", "bmp", "gif", "jpg", "png", "svg", "tiff"}:
        kind = "image"
    elif extension in {"txt", "csv"}:
        kind = "text"
    else:
        kind = "binary"
    return {"kind": kind, "extension": extension}


def canonize(value, req_type):
    """Create a Python identifier; browser URLs retain their original spelling."""
    return req_type.lower() + "_" + re.sub(r"[^a-zA-Z0-9_]", "_", value)


def load_api_requests(schema_directory, domain):
    import filesystem_utils
    from api_schema_utils import deserialize_api_request_from_schema_file

    requests = []
    for schema in sorted(filesystem_utils.read_files_from_path(schema_directory, r".*\.json$")):
        name, data = deserialize_api_request_from_schema_file(schema)
        position = data["Query"].find(domain)
        if position >= 0:
            requests.append((name, data))
    return requests


def build_discovery_document(requests, domain):
    paths = {"/" + request_fields(data, domain)["query"] for _, data in requests}
    routes = [{"path": path, "timeout_seconds": 60} for path in sorted(paths)]
    revision = hashlib.sha256(json.dumps(routes, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"schema_version": 1, "revision": "sha256:" + revision, "routes": routes}


def flatten_params(params):
    """Expose inherited defaults; the parameter closest to the query wins."""
    flattened = {}
    for value in params.values():
        if isinstance(value, dict):
            flattened.update(flatten_params(value))
    flattened.update({key: value for key, value in params.items()
                      if not isinstance(value, dict) and key != "SESSION_ID"})
    return flattened


def read_documentation_sections(index_path):
    path = Path(index_path)
    return re.split(r"(?m)(?=^## )", path.read_text()) if path.exists() else None


def query_documentation(sections, fields, description):
    if sections is not None:
        heading = "### " + fields["query"] + "/" + fields["method"]
        for section in sections:
            if any(line == heading or line.startswith(heading + " ") for line in section.splitlines()):
                return section.replace(f"[execute](/{fields['query']})", f"[configure]({fields['page_url']})").replace(heading, " -> ")
        return None  # An existing README controls query publication/withdrawal.
    return "\n\n".join(str(value) for value in description.values())


def build_browser_catalog(requests, domain, index_path):
    sections = read_documentation_sections(index_path)
    services, ungrouped, queries = {}, [], {}
    for name, data in requests:
        fields = request_fields(data, domain)
        documentation = query_documentation(sections, fields, data.get("Description", {}))
        if documentation is None:
            continue
        entry = {"name": name, "query": fields["query"], "method": fields["method"],
                 "action_url": "/" + fields["query"], "page_url": fields["page_url"],
                 "service_name": fields["service_name"], "service_url": fields["service_url"],
                 "params": flatten_params(fields["params"]), "documentation": documentation,
                 "response": response_presentation(data)}
        queries[fields["query_id"]] = entry
        service = fields["service_name"]
        if service:
            services.setdefault(service, {"name": service, "url": fields["service_url"], "queries": []})["queries"].append(entry)
        else:
            ungrouped.append(entry)
    for service in services.values():
        service["queries"].sort(key=lambda entry: (entry["query"], entry["method"]))
    return dict(sorted(services.items())), ungrouped, queries
