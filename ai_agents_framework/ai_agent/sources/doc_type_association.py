#!/usr/bin/env python

from pathlib import Path

CODE_EXTENSIONS = {
    "c", "cc", "cpp", "cxx", "h", "hpp", "cs", "go", "java", "js", "jsx",
    "kt", "kts", "lua", "php", "pl", "py", "r", "rb", "rs", "scala", "sh",
    "sql", "swift", "ts", "tsx", "vue", "zig",
}
TEXT_GROUPS = {
    "markdown": {"md", "markdown", "rst", "adoc"},
    "data": {"csv", "json", "jsonl", "toml", "tsv", "xml", "yaml", "yml"},
    "web": {"css", "htm", "html", "scss", "svg"},
    "document": {"log", "text", "txt"},
}

def document_type(path):
    """Return a text-compatible semantic document type for a filename."""
    extension = Path(path).suffix.lower().lstrip(".")
    if extension in CODE_EXTENSIONS:
        return "txt,code"
    for group, extensions in TEXT_GROUPS.items():
        if extension in extensions:
            return f"txt,{group}"
    return f"txt,{extension or 'document'}"
