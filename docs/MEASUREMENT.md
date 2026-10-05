# Measurement approach: first 30 days

**Metric: verified-answer rate.** This is the share of knowledge questions that get a confident, cited answer the user does not push back on. A question counts as verified when it is answered (not routed or refused), has at least one valid citation, and gets no thumbs-down, rejection or correction in its session. I'd track it daily for the first 30 days, because it combines the two things that decide whether people keep using the assistant: coverage (can it answer?) and trust (was the answer right?). Raw usage or latency alone can't show either.

It comes straight from data the system already logs. Each answer is a row in `messages` (status, confidence, `payload.citation_stats`). Pushback is the `feedback` column plus `gaps` rows of type `rejected` or `correction`. Guardrail-handled messages are excluded from the denominator, using `metrics.guardrail`.

How to read it:
- **Week 1** sets the baseline. After that, track it as a 7-day rolling number, split by source type and topic so gaps show up where content is missing.
- **Guard against gaming:** a rising rate could also mean users simply stopped giving feedback. So I'd pair it with a weekly audit of 20 randomly sampled "verified" answers, judged by hand against their citations, plus the golden-set eval (`/evals`) on every configuration change. Together these confirm that real accuracy is moving, not just reported satisfaction.
- **Actions:** a drop triggers a review of the low-confidence queue. Every resolved gap should become new or corrected source content.
