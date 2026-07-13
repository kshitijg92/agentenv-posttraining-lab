        # Task: repair_env_assignment_parser

        ## What It Measures

        Line-oriented parsing, explicit escaping, duplicate detection, and syntax validation.

        ## What It Does Not Measure

        Shell evaluation, variable expansion, export statements, filesystem loading, or full dotenv compatibility.

        ## Human Solve Estimate

        15-30 minutes for a strong Python engineer.

        ## Expected Meaningful Steps

        - Separate comment/blank handling from assignment parsing.
- Validate the key grammar and duplicate policy.
- Decode quoted values with a closed escape set without evaluating them.

        ## Public Check

        The visible values are simple unquoted strings and the seeded split/strip logic handles them.

        ## Hidden Validator

        The hidden tests cover Quoted escapes, literal equals and hashes, empty values, ordering, duplicates, malformed syntax, and invalid types.

        ## Known Shortcuts

        Stripping surrounding quotes passes simple examples but neither validates nor decodes the quoted grammar.

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
