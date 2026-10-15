from typing import Literal
from pydantic import BaseModel, Field


class GeneticNumberInput(BaseModel):
    raw_name: str = Field(min_length=1, max_length=255)
    examination_no: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    source_key: str | None = Field(default=None, max_length=255)


class GeneticNumbersRequest(BaseModel):
    examination_year: int = Field(ge=1900, le=2200)
    items: list[GeneticNumberInput] = Field(min_length=1, max_length=10000)


class GeneticExcelApply(GeneticNumbersRequest):
    upload_id: str = Field(pattern=r"^[a-f0-9]{32}\.xlsx$")
    selected_fields: list[Literal["header", "stages", "layout"]] = Field(default_factory=lambda: ["header", "stages", "layout"])
    selected_stage_fields: list[Literal["date", "kit", "performers", "sequencer", "comment"]] = Field(default_factory=lambda: ["date", "kit", "performers", "sequencer", "comment"])
    well_mappings: dict[str, str] = Field(default_factory=dict, max_length=40000)


class GeneticRtMapping(BaseModel):
    upload_id: str = Field(max_length=80)
    sample_key: str = Field(max_length=255)
    object_id: int = Field(gt=0)


class GeneticRtCommit(BaseModel):
    examination_year: int = Field(ge=1900, le=2200)
    object_ids: list[int] = Field(min_length=1, max_length=10000)
    upload_ids: list[str] = Field(min_length=1, max_length=10)
    mappings: list[GeneticRtMapping] = Field(default_factory=list, max_length=10000)
    excluded_samples: list["GeneticRtExclusion"] = Field(default_factory=list, max_length=10000)
    mode: Literal["attempt", "replace"] = "attempt"
    confirm_duplicate: bool = False


class GeneticRtExclusion(BaseModel):
    upload_id: str = Field(max_length=80)
    sample_key: str = Field(max_length=255)


GeneticRtCommit.model_rebuild()
