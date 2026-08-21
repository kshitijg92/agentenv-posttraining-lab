# Week 11 Learnings

## Integrity, Availability, And Relocatability Are Different Claims

A content hash proves that bytes match a declared identity once those bytes can
be found. It does not prove that a clean checkout contains them or that the
artifact graph can be moved to another filesystem location. Ignored stored
evidence can be locally auditable but unavailable to CI; absolute provenance
references can be internally consistent but non-relocatable.

Therefore a reproduction claim needs all three properties stated separately:

- integrity: did the loaded evidence match its pins?
- availability: does the target environment actually possess the evidence?
- relocatability: can references be resolved independently of the producer's
  original checkout path?

Passing local integrity checks must not be described as clean-checkout
reproduction when availability or relocatability is missing.
