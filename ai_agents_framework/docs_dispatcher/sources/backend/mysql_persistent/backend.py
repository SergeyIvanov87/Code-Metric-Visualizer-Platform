"""MySQL access and persistent file-storage backend composition."""

import base64
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from interfaces import Backend, RuntimeConfig
from interfaces.access import AccessRecordEntryInterface
from interfaces.store import StorageRecordEntryInterface
from interfaces_impl.access.mysql import MysqlAccessRecordEntry
from interfaces_impl.store.persistent import PersistentStorageRecordEntry
from interfaces.store.utils import decanonize_file_uri, file_uris_equal, prepare_doc_data


@dataclass(frozen=True)
class MysqlPersistentBackend(Backend):
    access: AccessRecordEntryInterface
    store: StorageRecordEntryInterface

    @classmethod
    @contextmanager
    def create_instance(cls, config: RuntimeConfig):
        with PersistentStorageRecordEntry.create_instance(config) as store:
            with MysqlAccessRecordEntry.create_instance(config) as access:
                yield cls(access=access, store=store)

    def _cleanup_failed_record(
        self,
        unique_id: int,
        original_error: Exception,
    ) -> None:
        rollback_errors = []
        # Remove storage first. If the process stops between cleanup steps,
        # synchronization can safely remove the remaining database-only row.
        for layer_name, records in (
            ("file storage", self.store),
            ("database", self.access),
        ):
            try:
                records.delete_records([unique_id], cascade_delete=False)
                if records.get_records([unique_id]):
                    rollback_errors.append(
                        f"record id={unique_id} remains in {layer_name}"
                    )
            except Exception as rollback_error:
                rollback_errors.append(f"{layer_name}: {rollback_error}")

        if rollback_errors:
            raise RuntimeError(
                f"{original_error}; rollback of record id={unique_id} failed: "
                f"{'; '.join(rollback_errors)}"
            ) from original_error


    def put_doc_by_uri(self, file_uri: str | Path, metadata_text: str = "", doc_type: str = "txt") -> dict:
        if file_uri is None:
            raise ValueError("file_uri is required when adding a document by URI")

        count_of_docs_to_insert = 1
        unique_id_candidates = self.access.create_unique_ids(count_of_docs_to_insert)
        uid = next(iter(unique_id_candidates))

        try:
            stored_record = self.store.init_record_from_path(
                file_uri,
                uid,
                parent_id=uid,
                offset=0,
                metadata_text=metadata_text,
                doc_type=doc_type,
            )
            if self.access.update_record_by_id(uid, stored_record) != 1:
                raise RuntimeError(f"Allocated record id={uid} disappeared from DB")
        except Exception as error:
            self._cleanup_failed_record(uid, error)
            raise

        return {"unique_id": uid}

    def put_doc_by_data(self, file_uri: str | Path | None, data: bytes, *, metadata_text: str = "", doc_type: str = "txt") -> dict:
        if file_uri is None and "base64" in doc_type:
            data = base64.b64decode(data)
        data = prepare_doc_data(data)

        count_of_docs_to_insert = 1
        unique_id_candidates = self.access.create_unique_ids(count_of_docs_to_insert)
        uid = next(iter(unique_id_candidates))

        try:
            stored_record = self.store.init_record_from_data(
                file_uri,
                uid,
                data,
                parent_id=uid,
                offset=0,
                metadata_text=metadata_text,
                doc_type=doc_type,
            )
            if self.access.update_record_by_id(uid, stored_record) != 1:
                raise RuntimeError(f"Allocated record id={uid} disappeared from DB")
        except Exception as error:
            self._cleanup_failed_record(uid, error)
            raise

        return {"unique_id": uid}


    def attach_doc_chunk(self, document_id: int, data: bytes, *, metadata_text: str = "") -> dict:
        parent_records = self.access.get_records([document_id])
        if len(parent_records) == 0:
            raise ValueError(f"Parent document id={document_id} does not exist in DB")
        parent = parent_records[0]
        if parent.parent_id != parent.id:
            raise ValueError(f"Record id={document_id} is not a full document")

        stored_records = self.store.get_records([document_id])
        if len(stored_records) == 0:
            raise ValueError(f"Parent document id={document_id} does not exist on a persistent storage")
        stored_parent = stored_records[0]
        if stored_parent.parent_id != stored_parent.id:
            raise ValueError(f"Storage record id={document_id} is not a full document")

        data = prepare_doc_data(data)
        if "base64" in parent.doc_type.split(','):
            data = base64.b64decode(data)

        # determine chunks offset and size
        parent_data = self.store.read_record_data(stored_parent)
        offset = parent_data.find(data)
        if offset < 0:
            raise ValueError(
                f"chunk does not belong to the parent document by ID: "
                f"{parent.id}, the chunk content cannot be found"
            )
        size = len(data)
        if stored_parent.size >= 0 and offset + size > stored_parent.size:
            raise ValueError(f"chunk with offset: {offset} and size: {size} does not fit into the parent document of size: {stored_parent.size}, type: {stored_parent.doc_type}")

        count_of_docs_to_insert = 1
        unique_id_candidates = self.access.create_unique_ids(count_of_docs_to_insert)
        uid = next(iter(unique_id_candidates))

        try:
            stored_record_chunk = self.store.init_record_from_data(
                stored_parent.file_uri,
                uid,
                data,
                offset=offset,
                parent_id=stored_parent.id,
                metadata_text=metadata_text,
            )
            if self.access.update_record_by_id(uid, stored_record_chunk) != 1:
                raise RuntimeError(f"Allocated record id={uid} disappeared from DB")
        except Exception as error:
            self._cleanup_failed_record(uid, error)
            raise

        return {"unique_id": uid}


    def delete_records(self, record_ids: Iterable[int]) -> tuple[int, int, list[int]]:
        store_deleted_count, store_non_deleted_id = self.store.delete_records(record_ids, True)
        access_deleted_count, access_non_deleted_id = self.access.delete_records(record_ids, True)
        missing_ids = list(
            dict.fromkeys([*store_non_deleted_id, *access_non_deleted_id])
        )
        return access_deleted_count, store_deleted_count, missing_ids

    def get_document_info(self, doc_ids: list[int]) -> dict[str, object]:
        unique_doc_ids = self._unique_ids(doc_ids)
        access_records_by_id = {
            int(record.id): record
            for record in self.access.get_records(unique_doc_ids)
        }
        store_records_by_id = {
            int(record.id): record
            for record in self.store.get_records(unique_doc_ids)
        }
        access_chunk_ids = self.access._get_chunk_ids(unique_doc_ids)
        store_chunk_ids = self.store._get_chunk_ids(unique_doc_ids)

        found: list[int] = []
        inconsistent: list[int] = []
        not_found: list[int] = []
        result: dict[str, object] = {
            "found": found,
            "inconsistent": inconsistent,
            "not_found": not_found,
        }

        for uid in unique_doc_ids:
            access_record = access_records_by_id.get(uid)
            store_record = store_records_by_id.get(uid)
            in_access = (
                access_record is not None
                and int(access_record.parent_id) == uid
            )
            in_store = (
                store_record is not None
                and int(store_record.parent_id) == uid
            )

            if in_access and in_store:
                found.append(uid)
                result[str(uid)] = {
                    "error_code": 0,
                    "status": "success",
                    "info": {
                        "file_uri": decanonize_file_uri(access_record.file_uri),
                        "type": access_record.doc_type,
                        "chunks": access_chunk_ids[uid],
                    },
                }
                continue

            if in_access:
                inconsistent.append(uid)
                result[str(uid)] = {
                    "error_code": 1,
                    "status": "Not found in the doc storage: file storage",
                    "info": {
                        "file_uri": decanonize_file_uri(access_record.file_uri),
                        "type": access_record.doc_type,
                        "chunks": access_chunk_ids[uid],
                    },
                }
            elif in_store:
                inconsistent.append(uid)
                result[str(uid)] = {
                    "error_code": 1,
                    "status": "Not found in the doc storage: database",
                    "info": {
                        "file_uri": decanonize_file_uri(store_record.file_uri),
                        "type": store_record.doc_type,
                        "chunks": store_chunk_ids[uid],
                    },
                }
            else:
                not_found.append(uid)
                result[str(uid)] = {
                    "error_code": -1,
                    "status": "The doc is absent or ID is incorrect",
                }

        return result

    def get_documents(self, offset: int = 0, limit: int = -1) -> dict[str, object]:
        if offset < 0:
            raise ValueError(f"offset must be greater than or equal to 0, got: {offset}")
        if limit < -1:
            raise ValueError(f"limit must be -1 or greater, got: {limit}")

        total_documents, document_rows = self.access.document_page(offset, limit)
        document_ids = [int(document.id) for document in document_rows]
        chunk_ids_by_document = self.access._get_chunk_ids(document_ids)
        documents = [
            {
                "id": int(document.id),
                "file_uri": decanonize_file_uri(document.file_uri),
                "type": document.doc_type,
                "chunks": chunk_ids_by_document[int(document.id)],
            }
            for document in document_rows
        ]
        returned_limit = len(documents)
        return {
            "offset": offset,
            "limit": returned_limit,
            "remaining": max(0, total_documents - offset - returned_limit),
            "docs": documents,
        }


    def read_ids(self, record_ids: Iterable[int]) -> dict[int, dict[str, object]]:
        requested_ids = self._unique_ids(record_ids)
        access_records_by_id = {
            int(record.id): record
            for record in self.access.get_records(requested_ids)
        }
        store_records_by_id = {
            int(record.id): record
            for record in self.store.get_records(requested_ids)
        }

        resolved_records: dict[int, tuple[int, int, int]] = {}
        results: dict[int, dict[str, object]] = {}

        for record_id in requested_ids:
            access_record = access_records_by_id.get(record_id)
            store_record = store_records_by_id.get(record_id)

            if access_record is None and store_record is None:
                results[record_id] = self._read_error(
                    record_id,
                    f"Record id={record_id} does not exist",
                )
                continue

            if access_record is not None and store_record is not None:
                differences = access_record.get_difference(store_record)
                parent_id = int(access_record.parent_id)
                offset = int(access_record.offset)
                size = int(access_record.size)
                if "parent_id" in differences:
                    results[record_id] = self._read_error(
                        record_id,
                        f"Record id={record_id} has inconsistent parent_id "
                        "between DB and file storage",
                    )
                    continue
                if (
                    parent_id != record_id
                    and any(
                        field_name in differences
                        for field_name in ("offset", "size")
                    )
                ):
                    results[record_id] = self._read_error(
                        record_id,
                        f"Chunk id={record_id} has inconsistent offset or size "
                        "between DB and file storage",
                    )
                    continue
                resolved_records[record_id] = (parent_id, offset, size)
                continue

            record = access_record if access_record is not None else store_record
            resolved_records[record_id] = (
                int(record.parent_id),
                int(record.offset),
                int(record.size),
            )

        document_ids = self._unique_ids(
            record_id if parent_id == record_id else parent_id
            for record_id, (parent_id, _, _) in resolved_records.items()
        )
        missing_document_ids = [
            document_id
            for document_id in document_ids
            if document_id not in store_records_by_id
        ]
        store_records_by_id.update(
            {
                int(record.id): record
                for record in self.store.get_records(missing_document_ids)
            }
        )

        payloads: dict[int, bytes] = {}
        payload_errors: dict[int, str] = {}
        for document_id in document_ids:
            document = store_records_by_id.get(document_id)
            if document is None:
                payload_errors[document_id] = (
                    f"Parent document id={document_id} does not exist in file storage"
                )
                continue
            if int(document.parent_id) != int(document.id):
                payload_errors[document_id] = (
                    f"Parent id={document_id} does not identify a full document "
                    "in file storage"
                )
                continue

            try:
                payloads[document_id] = self.store.read_record_data(document)
            except OSError as exc:
                payload_errors[document_id] = (
                    f"Cannot read parent document id={document_id} "
                    f"from file storage: {exc}"
                )

        for record_id, (parent_id, offset, size) in resolved_records.items():
            record_type = "document" if parent_id == record_id else "chunk"
            document_id = record_id if record_type == "document" else parent_id
            payload_error = payload_errors.get(document_id)
            if payload_error is not None:
                results[record_id] = self._read_error(record_id, payload_error)
                continue

            document_data = payloads[document_id]
            if record_type == "document":
                context_data = document_data
            else:
                if offset < 0 or size < 0:
                    results[record_id] = self._read_error(
                        record_id,
                        f"Chunk id={record_id} has invalid offset={offset} or size={size}",
                    )
                    continue
                chunk_end = offset + size
                if chunk_end > len(document_data):
                    results[record_id] = self._read_error(
                        record_id,
                        f"Chunk id={record_id} range [{offset}, {chunk_end}) "
                        f"exceeds parent document size {len(document_data)}",
                    )
                    continue
                context_data = document_data[offset:chunk_end]

            try:
                context = context_data.decode("utf-8")
            except UnicodeDecodeError as exc:
                results[record_id] = self._read_error(
                    record_id,
                    f"Record id={record_id} does not contain valid UTF-8 text: {exc}",
                )
                continue

            results[record_id] = {
                "id": record_id,
                "parent_id": parent_id,
                "record_type": record_type,
                "context": context,
                "error_code": 0,
                "status": "success",
            }

        return {record_id: results[record_id] for record_id in requested_ids}

    def synchronize(self) -> dict:
        self.store.ensure_root()
        access_records = self.access.get_all_records()
        storage_records = self.store.get_all_records()
        remaining_storage_records = dict(storage_records)

        record_ids_to_delete: list[int] = []
        records_to_update = {}

        for access_record in access_records:
            record_id = int(access_record.id)
            storage_record = remaining_storage_records.pop(record_id, None)
            if storage_record is None:
                record_ids_to_delete.append(record_id)
                continue

            differences = access_record.get_difference(storage_record)
            changed = False

            if (
                "file_uri" in differences
                and not file_uris_equal(
                    access_record.file_uri,
                    storage_record.file_uri,
                )
            ):
                access_record.file_uri = decanonize_file_uri(
                    str(storage_record.file_uri)
                )
                changed = True

            for field_name in ("offset", "size", "parent_id", "doc_type"):
                if field_name not in differences:
                    continue
                setattr(
                    access_record,
                    field_name,
                    getattr(storage_record, field_name),
                )
                changed = True

            if changed:
                records_to_update[record_id] = access_record

        deleted, _ = self.access.delete_records(
            record_ids_to_delete,
            cascade_delete=False,
        )
        updated = self.access.update_records_by_ids(records_to_update)
        created = self.access.create_records_by_ids(
            remaining_storage_records
        )

        return {
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "not_changed": len(storage_records) - updated - created,
            "initial DB records": len(access_records),
            "storage size": len(storage_records),
        }

    @staticmethod
    def _read_error(record_id: int, error_msg: str) -> dict[str, object]:
        return {
            "id": record_id,
            "error_code": -1,
            "status": "error",
            "error_msg": error_msg,
        }


    @staticmethod
    def _unique_ids(non_unique_ids: Iterable[int]) -> list[int]:
        return list(dict.fromkeys(non_unique_ids))
