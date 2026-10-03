import enum

class StorageRecordEntry(str,enum.Enum):
    doc_suffix = ".storage_bin"
    parent_id = "parentId"
    offset = "offset"
    size = "size"
    metadata = "metadata"
    doc_type = "doc_type"
