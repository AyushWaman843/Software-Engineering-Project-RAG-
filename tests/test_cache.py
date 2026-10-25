"""Tests for the content-keyed LLM result cache."""

import threading

import pytest

import cache
from cache import (
    CACHE_TTL_SECONDS,
    clear_scan_cache,
    get_cached_llm_result,
    make_cache_key,
    set_cached_llm_result,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_scan_cache()
    yield
    clear_scan_cache()


class TestMakeCacheKey:
    def test_same_inputs_give_same_key(self):
        assert make_cache_key("model", 1, "policy") == make_cache_key("model", 1, "policy")

    def test_any_part_changing_changes_the_key(self):
        base = make_cache_key("model", "v1", 0, "policy text", "terms text")
        assert make_cache_key("other", "v1", 0, "policy text", "terms text") != base
        assert make_cache_key("model", "v2", 0, "policy text", "terms text") != base
        assert make_cache_key("model", "v1", 1, "policy text", "terms text") != base
        assert make_cache_key("model", "v1", 0, "policy text!", "terms text") != base
        assert make_cache_key("model", "v1", 0, "policy text", "terms text!") != base

    def test_part_boundaries_are_unambiguous(self):
        assert make_cache_key("ab", "c") != make_cache_key("a", "bc")
        assert make_cache_key("a", "") != make_cache_key("", "a")

    def test_handles_unicode_and_lone_surrogates(self):
        assert make_cache_key("नीति", "\ud800")


class TestStore:
    def test_round_trip(self):
        set_cached_llm_result("k", {"score": 80, "indicators": {"a": {"status": "Found"}}})
        assert get_cached_llm_result("k") == {"score": 80, "indicators": {"a": {"status": "Found"}}}

    def test_miss_and_empty_key(self):
        assert get_cached_llm_result("missing") is None
        assert get_cached_llm_result("") is None

    def test_empty_values_are_not_cached(self):
        set_cached_llm_result("", {"score": 1})
        set_cached_llm_result("k", {})
        assert get_cached_llm_result("k") is None

    def test_callers_cannot_mutate_cached_data(self):
        original = {"indicators": {"a": {"status": "Found"}}}
        set_cached_llm_result("k", original)
        original["indicators"]["a"]["status"] = "Missing"
        first = get_cached_llm_result("k")
        assert first["indicators"]["a"]["status"] == "Found"
        first["indicators"]["a"]["status"] = "Partial"
        assert get_cached_llm_result("k")["indicators"]["a"]["status"] == "Found"

    def test_entries_expire_after_ttl(self):
        set_cached_llm_result("k", {"score": 1})
        cache._scan_cache["k"]["timestamp"] -= CACHE_TTL_SECONDS + 1
        assert get_cached_llm_result("k") is None
        assert "k" not in cache._scan_cache

    def test_least_recently_used_entry_is_evicted(self, monkeypatch):
        monkeypatch.setattr(cache, "MAX_CACHE_ENTRIES", 3)
        for name in ("a", "b", "c"):
            set_cached_llm_result(name, {"v": name})
        assert get_cached_llm_result("a")  # touching "a" makes "b" the oldest
        set_cached_llm_result("d", {"v": "d"})
        assert get_cached_llm_result("b") is None
        assert {n for n in "acd" if get_cached_llm_result(n)} == set("acd")

    def test_size_stays_bounded_under_concurrent_use(self, monkeypatch):
        monkeypatch.setattr(cache, "MAX_CACHE_ENTRIES", 20)
        errors = []

        def worker(offset):
            try:
                for i in range(200):
                    key = f"k{(offset + i) % 60}"
                    set_cached_llm_result(key, {"v": i})
                    get_cached_llm_result(key)
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n * 7,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(cache._scan_cache) <= 20
