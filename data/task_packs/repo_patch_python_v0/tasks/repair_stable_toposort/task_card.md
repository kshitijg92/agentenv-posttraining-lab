        # Task: repair_stable_toposort

        ## What It Measures

        Dependency reasoning, input validation, cycle detection, and deterministic tie-breaking.

        ## What It Does Not Measure

        Package resolution, concurrent scheduling, graph scale, or incremental builds.

        ## Human Solve Estimate

        15-30 minutes for a strong Python engineer.

        ## Expected Meaningful Steps

        - Validate and normalize the node and dependency iterables.
- Detect unknown, duplicate, self, and cyclic dependencies.
- Select ready nodes using original input order as the tie-break.

        ## Public Check

        The visible graph is already in dependency order, so the seeded implementation passes it.

        ## Hidden Validator

        The hidden tests cover Reordered graphs, stable ties, generators, cycles, malformed nodes, and malformed dependency mappings.

        ## Known Shortcuts

        Returning the input order passes the public chain but ignores the graph contract.

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
