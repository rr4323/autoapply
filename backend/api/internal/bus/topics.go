package bus

// Topic names — TDD.md §2's ten Redis Streams topics. One stream per
// event type; the message envelope (envelope.go) is the shape of every
// entry written to any of them.
const (
	TopicJDDiscovered        = "jd.discovered"
	TopicJDParsed            = "jd.parsed"
	TopicContextRetrieved    = "context.retrieved"
	TopicApplicationScored   = "application.scored"
	TopicPolicyDecision      = "policy.decision"
	TopicDocumentsGenerated  = "documents.generated"
	TopicFormFilled          = "form.filled"
	TopicApplicationTerminal = "application.terminal"
	TopicModelDriftDetected  = "model.drift_detected"
	TopicModelPromoted       = "model.promoted"
)
