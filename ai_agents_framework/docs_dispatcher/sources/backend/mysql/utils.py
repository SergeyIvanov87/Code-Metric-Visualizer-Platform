
def prepare_doc_data(document_data):
    if isinstance(document_data, str):
        document_data = document_data.strip().encode("utf-8")
    else:
        document_data = document_data.decode("utf-8").strip().encode("utf-8")
    return document_data
