# Two-Stage Guardrails and Choosing the Fail-Safe Direction

## What it is

Step 36's guardrail scan (`TDD.md` §14.1) is the third time this codebase uses the same deterministic-then-LLM shape: cheap heuristics run on everything, an LLM judge only runs on what the heuristics can't confidently resolve. Scoring split this into keyword-overlap (Step 27) + semantic signal (Step 28); groundedness split into the citation check (Step 35) + a future Ragas judge; the guardrail scan splits into Stage 1 regex/pattern matching + a Stage 2 Haiku judge. Same reason every time: the expensive/non-deterministic call only runs when the cheap deterministic pass genuinely can't decide.

## Verified example (from `backend/agents/src/agentos_agents/generator/guardrail.py`)

```python
async def scan_document(text, allowed_emails, allowed_urls, llm_client=None):
    markers = _find_injection_markers(text)
    if markers:
        return GuardrailResult(verdict=GuardrailVerdict.BLOCK, reasons=[...])

    off_emails, off_urls = _find_off_profile_contacts(text, allowed_emails, allowed_urls)
    if not off_emails and not off_urls:
        return GuardrailResult(verdict=GuardrailVerdict.PASS, reasons=["clean scan"])

    if llm_client is None:
        return GuardrailResult(verdict=GuardrailVerdict.BLOCK, reasons=[..., "no Stage 2 judge available"])

    is_injection = await _stage2_judge(llm_client, text, off_emails, off_urls)
    return GuardrailResult(
        verdict=GuardrailVerdict.BLOCK if is_injection else GuardrailVerdict.PASS,
        reasons=reasons, stage2_invoked=True,
    )
```

Tested by counting Stage 2 calls on a fake judge, not just checking the final verdict:
```python
class FakeJudge(LLMClient):
    def __init__(self, verdict): self.verdict = verdict; self.call_count = 0
    async def complete(self, system, user):
        self.call_count += 1
        return json.dumps({"injection": self.verdict, "rationale": "test"})

async def test_clean_document_...passes_without_stage2():
    judge = FakeJudge(verdict=True)  # would say "injection" if ever called — must not be
    result = await scan_document(f"... {PROFILE_EMAIL}", allowed_emails=[PROFILE_EMAIL], allowed_urls=[], llm_client=judge)
    assert result.stage2_invoked is False
    assert judge.call_count == 0
```
Setting the fake judge to the *wrong* answer and asserting it's never called is a stronger proof than checking `stage2_invoked is False` alone — if the code accidentally called the judge, the test would fail on the verdict too, not just silently pass with an unused mock.

## Two different "unresolved" situations, two different fail-safe directions

This function has two distinct "can't fully resolve this" cases, and picks a different safe default for each — worth noticing because the *reasoning*, not just the code, differs:

- **No judge available** (`llm_client=None`) for a borderline case → **BLOCK**. Nothing can confirm the flagged content is legitimate, so it doesn't ship.
- **Judge responds, but not in the expected JSON shape** → treated as **injection = True** → BLOCK. A judge that can't even answer the question it was asked isn't evidence of safety.

Both land on the same verdict (block) but for different reasons, and both follow the same underlying rule: **when a safety check can't complete, the unsafe direction is "let it through," not "block it."** `TDD.md` §7.4 states the identical principle for the (not-yet-built) bot-check detector — "false positives are the accepted failure direction, false negatives are not." Contrast this with `KeywordOverlapResult`'s *opposite* choice in Step 27 (no required skills listed → treated as *fully covered*, not zero) — the right fail-safe direction depends on which side of that particular check is actually the expensive mistake, not a single rule applied everywhere.

## Standard use case

Any two-stage cheap-filter-then-expensive-judge pipeline — and, more generally, any place a function has more than one "I couldn't fully decide" branch: it's worth asking, for each one separately, which wrong answer is worse, rather than defaulting all of them to the same fallback out of convenience.
