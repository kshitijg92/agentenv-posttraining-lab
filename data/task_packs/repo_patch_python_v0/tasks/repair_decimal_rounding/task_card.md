        # Task: repair_decimal_rounding

        ## What It Measures

        Exact numeric text validation, decimal rounding semantics, and canonical formatting.

        ## What It Does Not Measure

        Floating-point numerics, localization, currencies, arbitrary precision policy, or scientific notation.

        ## Human Solve Estimate

        15-30 minutes for a strong Python engineer.

        ## Expected Meaningful Steps

        - Validate the textual grammar before numeric conversion.
- Use decimal half-even quantization with sufficient precision.
- Canonicalize fixed width and signed zero.

        ## Public Check

        The visible value has no binary-representation-sensitive tie, so float formatting passes.

        ## Hidden Validator

        The hidden tests cover Binary float counterexamples, half-even ties, large values, fixed width, negative zero, and malformed inputs.

        ## Known Shortcuts

        Converting through float passes ordinary decimals but changes exact decimal rounding and large-number precision.

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
