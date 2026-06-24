# Task: repair_config_precedence

## What It Measures

This task measures whether a patch can repair a small two-module configuration
loader while preserving a visible precedence and validation contract. It
requires coordinating constants in `settings.py` with parsing and validation in
`config_loader.py`.

## What It Does Not Measure

This task does not measure framework integration, secrets management, TOML/YAML
parsing, nested config schemas, command-line parsing, network behavior, or
production configuration migration.

## Human Solve Estimate

20-35 minutes for a strong Python engineer.

## Expected Meaningful Steps

- Inspect the `Settings` dataclass and environment mapping in `settings.py`.
- Inspect the visible `load_settings(...)` docstring in `config_loader.py`.
- Ensure JSON config keys are limited to `host`, `port`, and `debug`.
- Apply precedence as environment variables over JSON config over defaults.
- Validate `host`, `port`, and `debug` according to the documented types and
  accepted string forms.
- Keep calls independent by returning a fresh `Settings` instance without
  mutating shared defaults.

## Public Check

The public tests verify:

- default settings are returned when no config path and an empty environment are
  supplied,
- a JSON config can override default `host` and `port`,
- `APP_PORT` overrides a JSON config value,
- an out-of-range port raises `ValueError`.

## Hidden Validator

The hidden validator checks:

- all three environment variables override config values,
- defaults, partial JSON config, and partial environment overrides are merged,
- `debug` accepts only booleans and the exact strings `"true"` and `"false"`,
- unsupported debug strings such as `"1"` raise `ValueError`,
- unknown JSON config keys raise `ValueError`,
- boolean ports are rejected even though `bool` is an `int` subclass in Python,
- repeated calls do not leak state across settings loads,
- a missing explicit config path raises `FileNotFoundError`.

The hidden validator does not require exact error-message wording.

## Known Shortcuts

A patch can pass public tests by supporting only the default path, config
`host`/`port`, `APP_PORT`, and basic port range validation. Hidden tests reject
that shortcut because it misses full environment precedence and validation
edges.

A patch can also pass public tests while ignoring unknown config keys or treating
boolean ports as integers. Hidden tests reject both.

## Oracle Summary

The oracle patch completes the environment mapping, rejects unknown config keys,
rejects boolean ports, parses only the accepted debug values, and returns a new
`Settings` object for each call.

## Bad Control Summary

`bad_noop.patch` leaves the seeded implementation unchanged. It passes the
public tests but fails hidden tests because it supports only a subset of the
visible contract.

`bad_public_only.patch` implements a plausible shortcut: when `APP_PORT` is
present it merges environment variables into the config-derived values, but when
only `APP_HOST` or `APP_DEBUG` is present it treats environment as a separate
source and drops config-derived values back to defaults. It passes public tests
but fails the mixed default/config/environment hidden case.

## Flake Risks

The task should be deterministic. It uses local temporary JSON files, explicit
environment mappings passed as dictionaries, pure Python parsing, no network, no
randomness, and no wall-clock assertions.

## Provenance

Self-authored synthetic task, created on a private machine. Does not use
employer-private, third-party-proprietary, or benchmark-heldout material.
