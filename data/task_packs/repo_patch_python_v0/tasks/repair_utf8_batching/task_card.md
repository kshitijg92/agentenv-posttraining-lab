        # Task: repair_utf8_batching

        ## What It Measures

        Greedy resource-constrained batching, UTF-8 accounting, and iterable validation.

        ## What It Does Not Measure

        Tokenization, compression, asynchronous queues, network packets, or streaming backpressure.

        ## Human Solve Estimate

        15-30 minutes for a strong Python engineer.

        ## Expected Meaningful Steps

        - Validate limits separately from iterable contents.
- Measure encoded bytes rather than Python character count.
- Apply both constraints greedily without mutating the source.

        ## Public Check

        The visible strings are ASCII, so character count happens to equal UTF-8 byte count.

        ## Hidden Validator

        The hidden tests cover Multibyte Unicode, generators, exact boundaries, oversized records, invalid limits, and invalid record types.

        ## Known Shortcuts

        Using len(record) passes ASCII examples but undercounts multibyte records.

        ## Oracle Summary

        The oracle implements the complete public instruction with deterministic
        standard-library behavior and explicit ValueError normalization.

        ## Bad Control Summary

        The no-op preserves the seeded bug. The public-only control adds shallow
        validation while retaining the shortcut exposed by the hidden validator.

        ## Agent Control Summary

        The task carries the standard happy, malformed-output, and recoverable
        tool-error scripts.

        ## Flake Risks

        Pure deterministic in-memory behavior with no time, randomness, locale,
        network, or filesystem dependence.

        ## Heldout Handling

        This task is in the frozen heldout-private slice. Its model outcomes may
        not be used to change training data, prompts, decoding, hyperparameters,
        task contracts, or the paired base/adapter evaluation configuration.

        ## Provenance

        Self-authored synthetic task with no employer-private, proprietary, or
        benchmark-heldout material.
