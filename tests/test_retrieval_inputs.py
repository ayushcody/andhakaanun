"""Jurisdiction detection, keyword fallback retrieval and the cache key."""

from apps.api.services.cache import CacheService
from apps.api.services.fallback_store import FALLBACK_LAWS, keyword_search
from apps.api.services.jurisdiction import detect_jurisdiction, quick_detect
from apps.api.services.retrieval import retrieve_laws


def test_quick_detect_returns_badges_for_traffic_offences(hit_and_run: str) -> None:
    labels = [b["label"] for b in quick_detect(hit_and_run)]
    assert "IPC 279" in labels
    assert "MVA 184" in labels
    assert len(labels) <= 6  # the UI shows at most six badges


def test_quick_detect_ignores_text_without_offence_keywords() -> None:
    assert quick_detect("We had lunch and went home.") == []


async def test_detect_jurisdiction_finds_domains_sections_and_location(hit_and_run: str) -> None:
    result = await detect_jurisdiction(hit_and_run, "Pune")
    assert result.detected_domains == ["criminal", "traffic_criminal"]
    assert "IPC_279" in result.matched_sections
    assert result.method == "keyword"
    assert result.location == "Pune"
    assert 0.0 <= result.confidence <= 1.0


async def test_detect_jurisdiction_with_no_signals_reports_none() -> None:
    result = await detect_jurisdiction(
        "My neighbour keeps playing loud music at night and we argued about it."
    )
    assert result.detected_domains == []
    assert result.method == "none"


def test_keyword_search_matches_fraud_to_cheating_section() -> None:
    ids = [law.section_id for law in keyword_search("it was a fraud and a scam")]
    assert ids == ["IPC_420"]


def test_keyword_search_respects_domain_filter_and_top_k(hit_and_run: str) -> None:
    traffic = keyword_search(hit_and_run, domains=["traffic_criminal"])
    assert traffic
    assert all(law.domain == "traffic_criminal" for law in traffic)
    assert len(keyword_search(hit_and_run, top_k=1)) == 1


def test_fallback_store_entries_are_complete() -> None:
    for key, law in FALLBACK_LAWS.items():
        assert law.section_id, key
        assert law.full_text, key
        assert law.keywords, key


async def test_retrieve_laws_falls_back_to_keywords_without_pinecone(hit_and_run: str) -> None:
    laws, meta = await retrieve_laws(hit_and_run, domains=["traffic_criminal"], pinecone_index=None)
    assert meta["source"] == "keyword_fallback"
    assert meta["fallback_used"] is True
    assert {law.section_id for law in laws} >= {"IPC_279"}
    assert all(law.score == 0.5 for law in laws)  # neutral score for keyword hits


def test_cache_key_is_normalised() -> None:
    assert CacheService.make_key(" Hello ", "Pune") == CacheService.make_key("hello", "pune ")
    assert CacheService.make_key("a", "x") != CacheService.make_key("a", "y")


async def test_cache_without_redis_is_a_no_op() -> None:
    cache = CacheService(None)
    assert cache.is_available is False
    assert await cache.get("text", "loc") is None
