from agentos_agents.generator.citation import (
    check_document_groundedness,
    parse_tagged_claims,
)
from agentos_agents.generator.prompt import RetrievedChunkRef

CHUNK = RetrievedChunkRef(
    chunk_id="c1",
    source_section="Eng @ Acme",
    text="Led the backend platform team using Go and PostgreSQL",
)


def test_parse_tagged_claims_extracts_text_and_chunk_id():
    text = (
        "Led the backend platform team using Go.[chunk:c1] "
        "Owned the on-call rotation.[chunk:c2]"
    )

    claims = parse_tagged_claims(text)

    assert len(claims) == 2
    assert claims[0].text == "Led the backend platform team using Go."
    assert claims[0].chunk_id == "c1"
    assert claims[1].text == "Owned the on-call rotation."
    assert claims[1].chunk_id == "c2"


def test_parse_tagged_claims_ignores_untagged_trailing_text():
    text = "Led the backend platform team.[chunk:c1] some stray untagged text"

    claims = parse_tagged_claims(text)

    assert len(claims) == 1  # the untagged trailing text is not a claim


def test_grounded_claim_passes():
    generated = "Led the backend platform team using Go.[chunk:c1]"

    report = check_document_groundedness(generated, [CHUNK])

    assert report.all_grounded is True
    assert report.results[0].grounded is True
    assert report.results[0].missing_key_terms == []


def test_fabricated_claim_fails():
    generated = (
        "Architected a fraud detection ML pipeline that saved $2M annually.[chunk:c1]"
    )

    report = check_document_groundedness(generated, [CHUNK])

    assert report.all_grounded is False
    result = report.results[0]
    assert result.grounded is False
    assert result.matched_key_terms == []  # zero overlap with the cited chunk
    assert len(result.missing_key_terms) > 0


def test_partially_grounded_claim_above_threshold_still_passes():
    # 4 of 6 key terms (led, backend, platform, team) are in the chunk;
    # "shipped" and "features" are not — a real but partial overlap that
    # still clears the 0.6 default threshold (4/6 = 0.667).
    generated = "Led the backend platform team and shipped features.[chunk:c1]"

    report = check_document_groundedness(generated, [CHUNK])

    result = report.results[0]
    assert result.grounded is True
    assert set(result.matched_key_terms) == {"led", "backend", "platform", "team"}
    assert set(result.missing_key_terms) == {"shipped", "features"}


def test_partially_grounded_claim_below_threshold_fails():
    # 4 of 8 key terms match (4/8 = 0.5, below the 0.6 default threshold)
    # — some real overlap, but not enough to count as grounded.
    generated = (
        "Led the backend platform team and mentored five junior engineers.[chunk:c1]"
    )

    report = check_document_groundedness(generated, [CHUNK])

    result = report.results[0]
    assert result.grounded is False
    assert len(result.matched_key_terms) > 0  # some real overlap ...
    assert len(result.missing_key_terms) > 0  # ... but not enough


def test_claim_citing_an_unsupplied_chunk_id_is_ungrounded():
    generated = "Led the backend platform team using Go.[chunk:c999]"

    report = check_document_groundedness(generated, [CHUNK])  # c999 was never supplied

    assert report.all_grounded is False
    assert report.results[0].grounded is False


def test_multiple_claims_mixed_groundedness():
    generated = (
        "Led the backend platform team using Go.[chunk:c1] "
        "Invented a time machine to ship features faster.[chunk:c1]"
    )

    report = check_document_groundedness(generated, [CHUNK])

    assert len(report.results) == 2
    assert report.all_grounded is False
    assert len(report.ungrounded_claims) == 1
    assert report.results[0].grounded is True
    assert report.results[1].grounded is False
