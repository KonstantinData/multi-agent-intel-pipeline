# Heuristic Promotion Policy

Promotion from candidate to active requires:
- at least 3 successful uses across relevant tasks
- no critical regressions linked to the heuristic
- baseline-safe replay performance

Demotion triggers:
- repeated failure mode reappearance
- measurable regression vs baseline
- conflict with newer validated policy
