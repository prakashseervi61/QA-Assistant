"""Tests for QueryRequest metadata_filter validation."""

import pytest

from src.application.dto.requests import QueryRequest


def test_valid_flat_filter():
    req = QueryRequest(
        question="test", metadata_filter={"document_id": "abc"}
    )
    assert req.metadata_filter == {"document_id": "abc"}


def test_none_filter_allowed():
    req = QueryRequest(question="test", metadata_filter=None)
    assert req.metadata_filter is None


def test_rejects_nested_dict():
    with pytest.raises(Exception):
        QueryRequest(
            question="test", metadata_filter={"key": {"nested": "value"}}
        )


def test_rejects_list_value():
    with pytest.raises(Exception):
        QueryRequest(question="test", metadata_filter={"key": [1, 2, 3]})


def test_rejects_non_str_key():
    with pytest.raises(Exception):
        QueryRequest(question="test", metadata_filter={123: "value"})


def test_accepts_all_flat_types():
    req = QueryRequest(
        question="test",
        metadata_filter={
            "str_key": "hello",
            "int_key": 42,
            "float_key": 3.14,
            "bool_key": True,
        },
    )
    assert req.metadata_filter is not None
    assert len(req.metadata_filter) == 4
