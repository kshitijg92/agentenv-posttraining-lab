        # Task: repair_latest_record_selection

        ## What It Measures

        Version-aware aggregation, stable identity ordering, mapping validation, and copy boundaries.

        ## What It Does Not Measure

        Persistent storage, distributed conflict resolution, timestamps, tombstones, or deep copying payloads.

        ## Human Solve Estimate

        15-30 minutes for a strong Python engineer.

        ## Expected Meaningful Steps

        - Validate every record before using its identity and version.
- Track seen versions separately from the current maximum.
- Preserve first-id order while returning fresh record dictionaries.

        ## Public Check

        The visible versions arrive in ascending order, so last-write-wins appears correct.

        ## Hidden Validator

        The hidden tests cover Out-of-order versions, interleaved identities, generators, duplicate versions, exact keys, invalid fields, and copy behavior.

        ## Known Shortcuts

        Keeping the last occurrence passes ordered input but does not select the highest version.

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
