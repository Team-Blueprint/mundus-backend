from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ReporterFlagCreate(BaseModel):
    site_id: int
    note: str | None = None


class ReporterFlagResponse(BaseModel):
    id: int
    site_id: int
    reporter_id: int
    reporter_name: str | None = None
    timestamp: datetime
    note: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_custom(cls, flag):
        reporter_name = flag.reporter.full_name if flag.reporter else None
        return cls(
            id=flag.id,
            site_id=flag.site_id,
            reporter_id=flag.reporter_id,
            reporter_name=reporter_name,
            timestamp=flag.timestamp,
            note=flag.note,
        )

