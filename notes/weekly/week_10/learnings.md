# Week 10 Learnings

## Review Dimensions Do Not Necessarily Need Review Artifacts

Prefix quality and action efficiency initially looked like separate stages
because they answer different questions. They nevertheless inspect the same
semantic object: the retained positive-SFT prefix. A second review artifact
duplicated source identity, messages, review state, manifests, and CLI
surfaces without creating a new source of evidence.

The cleaner boundary is one review row with two decisions. Prefix review owns
whether a contiguous prefix is eligible and where it ends. An optional embedded
efficiency judgment owns whether every retained action has a defensible causal
role.

The durable rule is:

```text
Create a new review artifact when the evidence unit or authority changes.
Add a review dimension when the same reviewer-facing evidence unit is judged
under another rubric.
```

Tokenization does not create a new semantic evidence unit. Token counts may
help prioritize or describe examples, but they should not force a
post-materialization review layer.

## Absence Can Be Sufficient State

An accepted prefix with no embedded efficiency judgment is pending. A
non-accepted prefix has no applicable efficiency judgment. These meanings are
derivable from the prefix decision, so persisting another review-status field
would add drift rather than clarity.

## Regenerate At Freeze Boundaries

Mutable reviews should not trigger export and materialization regeneration
after every edit. Populate and validate the combined review first, then rebuild
dependent derived artifacts once at the experiment freeze boundary. This keeps
provenance meaningful without making an evolving learning lab ceremonially
slow.
