        # Task: repair_json_pointer_lookup

        ## What It Measures

        Syntax-aware path decoding, typed container traversal, and failure normalization.

        ## What It Does Not Measure

        JSON parsing, mutation, JSON Patch, URI fragments, or arbitrary object attribute access.

        ## Human Solve Estimate

        15-30 minutes for a strong Python engineer.

        ## Expected Meaningful Steps

        - Parse the pointer without stripping meaningful empty segments.
- Decode only the two declared tilde escapes.
- Distinguish mapping keys from canonical list indexes.

        ## Public Check

        The public case contains one unescaped mapping key, which the seed handles.

        ## Hidden Validator

        The hidden tests cover Root lookup, escaped keys, empty keys, list traversal, malformed escapes, missing paths, and scalar traversal.

        ## Known Shortcuts

        Naively stripping and splitting slashes passes the public lookup but changes pointer syntax and cannot index lists.

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
