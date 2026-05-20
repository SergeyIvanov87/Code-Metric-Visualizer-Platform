from sqlalchemy import JSON, BigInteger, Column, Integer, String

from .database import Base


class FileRecord(Base):
    __tablename__ = "file_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_path = Column(String(2048), nullable=False)
    offset = Column(BigInteger, nullable=False, default=-1)
    size = Column(BigInteger, nullable=False, default=-1)
    parent_id = Column(BigInteger, nullable=False, default=0)
    metadata_json = Column(JSON, nullable=True)

    def __repr__(self) -> str:
        return (
            f"FileRecord("
            f"id={self.id}, "
            f"path='{self.file_path}', "
            f"offset={self.offset}, "
            f"size={self.size}, "
            f"parent_id={self.parent_id})"
        )
