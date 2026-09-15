
def prepare_doc_data(document_data):
    if isinstance(document_data, str):
        document_data = document_data.strip().encode("utf-8")
    else:
        document_data = document_data.decode("utf-8").strip().encode("utf-8")
    return document_data


def get_symbols_canonization_dict():
    return { "?":"%question%",
             "<":"%left-angle-bracket%",
             ">":"%right-angle-bracket%",
             "/":"%slash%",
             '\\' :"%backslash%",
             "|":"%pipe%",
             "*":"%asterisk%",
             ":":"%colon%"
    }

def get_symbol_decanonization_dict():
    reverse_dict = {}
    for k,v in get_symbols_canonization_dict().items():
        reverse_dict[v] = k
    return reverse_dict

def canonize_file_uri(file_uri):
    file_uri = str(file_uri)
    canonize_map = get_symbols_canonization_dict()
    for k,v in canonize_map.items():
        file_uri = file_uri.replace(k, v)
    return file_uri


def decanonize_file_uri(file_uri):
    file_uri = str(file_uri)
    decanonize_map = get_symbol_decanonization_dict()
    for k,v in decanonize_map.items():
        file_uri = file_uri.replace(k, v)
    return file_uri


def file_uris_equal(first, second):
    """Compare DB and storage forms of a file URI."""
    return canonize_file_uri(first) == canonize_file_uri(second)
