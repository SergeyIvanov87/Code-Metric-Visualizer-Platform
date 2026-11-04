#!/usr/bin/env python

from pathlib import Path

CODE_EXTENSIONS = {
    "c", "cc", "cpp", "cxx", "h", "hpp", "cs", "go", "java", "js", "jsx",
    "kt", "kts", "lua", "php", "pl", "py", "r", "rb", "rs", "scala", "sh",
    "sql", "swift", "ts", "tsx", "vue", "zig",
}
IMAGE_EXTENSIONS = {
    "apng", "arw", "avif", "bmp", "bpg", "cr2", "cr3", "cur", "dcm",
    "dds", "dib", "djvu", "dng", "emf", "eps", "exr", "fits", "flif",
    "gif", "hdr", "heic", "heif", "ico", "icns", "j2c", "j2k", "jfif",
    "jp2", "jpc", "jpe", "jpeg", "jpf", "jpg", "jpm", "jpx", "jxl",
    "mng", "nef", "orf", "pbm", "pcd", "pcx", "pef", "pgm", "png",
    "pnm", "ppm", "psd", "qoi", "raf", "ras", "raw", "rgb", "rgba",
    "sgi", "sr2", "svg", "svgz", "tga", "tif", "tiff", "wbmp", "webp",
    "wmf", "xbm", "xcf", "xpm",
}
TEXT_GROUPS = {
    "markdown": {"md", "markdown", "rst", "adoc"},
    "data": {"csv", "json", "jsonl", "toml", "tsv", "xml", "yaml", "yml"},
    "web": {"css", "htm", "html", "scss"},
    "document": {"log", "text", "txt"},
}

def document_type(path):
    """Return the semantic category and extension for a filename."""
    extension = Path(path).suffix.lower().lstrip(".")
    if extension in IMAGE_EXTENSIONS:
        return f"image,{extension}"
    if extension in CODE_EXTENSIONS:
        return "txt,code"
    for group, extensions in TEXT_GROUPS.items():
        if extension in extensions:
            return f"txt,{group}"
    return f"txt,{extension or 'document'}"
