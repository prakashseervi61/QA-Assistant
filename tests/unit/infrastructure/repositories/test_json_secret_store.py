"""Tests for the JSON-backed secret store."""

import json

import pytest

from src.infrastructure.repositories.json_secret_store import JsonSecretStore


class TestGetApiKey:
    def test_returns_none_when_file_absent(self, tmp_path):
        store = JsonSecretStore(tmp_path / "secrets.json")
        assert store.get_api_key() is None

    def test_round_trips_a_key(self, tmp_path):
        store = JsonSecretStore(tmp_path / "secrets.json")
        store.set_api_key("AIzaSyExampleKey123")
        assert store.get_api_key() == "AIzaSyExampleKey123"

    def test_replaces_a_previous_key(self, tmp_path):
        store = JsonSecretStore(tmp_path / "secrets.json")
        store.set_api_key("first-key-value")
        store.set_api_key("second-key-value")
        assert store.get_api_key() == "second-key-value"

    def test_treats_corrupt_json_as_no_key(self, tmp_path):
        path = tmp_path / "secrets.json"
        path.write_text("{not json at all", encoding="utf-8")
        # A corrupt file must not stop the app booting; it falls back to env.
        assert JsonSecretStore(path).get_api_key() is None

    def test_treats_blank_key_as_no_key(self, tmp_path):
        path = tmp_path / "secrets.json"
        path.write_text(json.dumps({"gemini_api_key": "   "}), encoding="utf-8")
        assert JsonSecretStore(path).get_api_key() is None

    def test_ignores_a_non_string_key(self, tmp_path):
        path = tmp_path / "secrets.json"
        path.write_text(json.dumps({"gemini_api_key": 12345}), encoding="utf-8")
        assert JsonSecretStore(path).get_api_key() is None

    def test_creates_parent_directories(self, tmp_path):
        store = JsonSecretStore(tmp_path / "nested" / "deeper" / "secrets.json")
        store.set_api_key("a-key-long-enough")
        assert store.get_api_key() == "a-key-long-enough"


class TestClearApiKey:
    def test_removes_the_key(self, tmp_path):
        store = JsonSecretStore(tmp_path / "secrets.json")
        store.set_api_key("a-key-long-enough")
        store.clear_api_key()
        assert store.get_api_key() is None

    def test_clearing_an_empty_store_is_not_an_error(self, tmp_path):
        JsonSecretStore(tmp_path / "secrets.json").clear_api_key()

    def test_leaves_no_temp_files_behind(self, tmp_path):
        store = JsonSecretStore(tmp_path / "secrets.json")
        store.set_api_key("a-key-long-enough")
        store.clear_api_key()
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []


class TestAtomicWrite:
    def test_write_never_leaves_a_partial_file(self, tmp_path):
        # The temp-then-rename write means a reader only ever sees a complete
        # file. Overwriting repeatedly must not corrupt the result.
        store = JsonSecretStore(tmp_path / "secrets.json")
        for i in range(20):
            store.set_api_key(f"key-number-{i:03d}")
            assert store.get_api_key() == f"key-number-{i:03d}"

    @pytest.mark.parametrize("bad_key", ["", "   "])
    def test_blank_values_are_stored_but_read_back_as_absent(self, tmp_path, bad_key):
        # Storage stays honest; it is the API layer that rejects blanks before
        # they get here, so this only asserts no crash.
        store = JsonSecretStore(tmp_path / "secrets.json")
        store.set_api_key(bad_key)
        assert store.get_api_key() is None
