"""Topic names — TDD.md §2's ten Redis Streams topics, mirroring
backend/api/internal/bus/topics.go. Kept as a second, hand-copied list
(Go and Python can't share a source file) rather than a shared config —
if a topic is ever renamed, both files need the same edit; this is the
same "two lists that must stay in sync" shape as the migration-file
lists fixed in Step 16, just across languages instead of within one.
"""

TOPIC_JD_DISCOVERED = "jd.discovered"
TOPIC_JD_PARSED = "jd.parsed"
TOPIC_CONTEXT_RETRIEVED = "context.retrieved"
TOPIC_APPLICATION_SCORED = "application.scored"
TOPIC_POLICY_DECISION = "policy.decision"
TOPIC_DOCUMENTS_GENERATED = "documents.generated"
TOPIC_FORM_FILLED = "form.filled"
TOPIC_APPLICATION_TERMINAL = "application.terminal"
TOPIC_MODEL_DRIFT_DETECTED = "model.drift_detected"
TOPIC_MODEL_PROMOTED = "model.promoted"
