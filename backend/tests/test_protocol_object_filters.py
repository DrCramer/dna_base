import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.api.protocols import _csv_strings, _object_conditions, _rcsme_boundary, _unique_text_options


def test_number_list_is_trimmed_and_deduplicated_case_insensitively():
    assert _csv_strings(" 7600-1,7601-1,7600-1, A-2,a-2, ") == ["7600-1", "7601-1", "A-2"]


def test_description_options_are_trimmed_sorted_and_deduplicated():
    assert _unique_text_options([" кость ", "Горелая кость", "КОСТЬ", None, ""]) == ["Горелая кость", "кость"]


def test_rcsme_boundaries_are_natural_numeric_keys():
    assert _rcsme_boundary("999-1") == (999, 1)
    assert _rcsme_boundary("1000") == (1000, 0)
    assert _rcsme_boundary("1001-12") == (1001, 12)


def test_invalid_rcsme_boundary_is_rejected():
    with pytest.raises(HTTPException, match="формат"):
        _rcsme_boundary("7600-")


def test_object_filters_are_combined_with_and():
    conditions = _object_conditions(
        party_ids=[204, 205],
        selected_ids=[],
        q=None,
        description="кость",
        rcsme_from="999-1",
        rcsme_to="1001-1",
        numbers=["1000-1"],
        object_type="кость",
        box_no="7",
        quick=None,
    )
    sql = " AND ".join(
        str(condition.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for condition in conditions
    )

    assert "objects.party_id IN (204, 205)" in sql
    assert "lower(trim(objects.rcsme_reg_no)) IN ('1000-1')" in sql
    assert "lower(trim(objects.object_description)) = 'кость'" in sql
    assert ">= 1" in sql
    assert "<= 1" in sql
