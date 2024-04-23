#!/usr/bin/python

import json
import os

def get_context_type_ext_mapping():
    return {"image/apng":"apng",
               "application/epub+zip":"epub",
               "application/gzip":"gz",
               "application/json":"json",
               "application/msword":"doc",
               "application/octet-stream":"bin",
               "application/pdf":"pdg",
               "application/vnd.oasis.opendocument.spreadsheet":"ods",
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document":"docx",
               "application/x-bzip":"bz",
               "application/x-bzip2":"bz2",
               "application/x-csh":"csh",
               "application/xml":"xml",
               "application/zip":"zip",

               "image/bmp":"bmp",
               "image/gif":"gif",
               "image/jpeg":"jpg",
               "image/png":"png",
               "image/svg+xml":"svg",
               "image/tiff":"tiff",

               "text/csv":"csv",
               "text/html":"html",
               "text/plain":"txt",
    }

def file_extension_from_content_type(content_type):
    mapping = get_context_type_ext_mapping()
    if content_type not in mapping.keys():
        raise KeyError(f"Content-Type: {content_type} is not found in the file extension mapping table")
    return mapping[content_type]

def file_extension_from_content_type_or_default(api_query, default):
    content_file_extension=""
    if "Content-Type" in api_query:
        content_file_extension = file_extension_from_content_type(api_query["Content-Type"])
    else:
        content_file_extension = default
    return content_file_extension


def content_type_from_file_extension(file_extension):
    content_type = ""
    for k, v in get_context_type_ext_mapping().items():
        if v == file_extension:
            content_type = k
            break

    if content_type == "":
        raise KeyError(f"The file extension: {file_extension} is not found in the Content-Type mapping table")
    return content_type


def deserialize_api_request_from_schema_file(api_request_schema_path):
    must_have_fields=["Method", "Query", "Params"]
    request = ""
    name = ""
    with open(api_request_schema_path, "r") as file:
        try:
            request = json.load(file)
            for f in must_have_fields:
                if f not in request:
                    raise ValueError(f"API schema must describe attribute: {f}. Check the schema in: {api_request_schema_path}")
            name = os.path.splitext(os.path.basename(api_request_schema_path))[0]
        except json.decoder.JSONDecodeError as e:
            raise Exception(f"Error: {str(e)} in file: {api_request_schema_path}")
    return name, request
