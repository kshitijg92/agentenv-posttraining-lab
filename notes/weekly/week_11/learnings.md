# Week 11 Learnings

## Internal Validity Is Not Canonical Reproduction

A deep loader can prove that an artifact graph is self-consistent: child hashes
match, lineage resolves, attempts agree with parents, and derived outcomes can
be reconstructed. It cannot prove that this graph is the experiment result we
intended to preserve when multiple internally valid runs exist.

Canonical reproduction therefore needs one small external designation of the
accepted top-level artifacts and expected decision. That designation should pin
the outer boundaries and let existing manifests retain ownership of their
internal provenance; copying the full graph would create competing authority.

## Semantic And Byte Equality Answer Different Questions

Reconstructing `abstained / complete_tie` proves that the archived evidence
still supports the same policy-selection decision. Regenerating identical
Markdown bytes proves that the report renderer still presents that evidence in
the designated canonical form. Either check can pass while the other fails, so
the reproduction claim requires both and reports them separately.
