from agentenv.security.secrets import (
    REDACTED_SECRET,
    is_sensitive_env_name,
    redact_jsonable,
    redact_secrets,
    scrubbed_subprocess_env,
)


CANARY = "agentenv-canary-secret-000000000000"


def test_sensitive_env_name_detection() -> None:
    assert is_sensitive_env_name("AGENTENV_MODEL_API_KEY")
    assert is_sensitive_env_name("HF_TOKEN")
    assert is_sensitive_env_name("AWS_SECRET_ACCESS_KEY")
    assert is_sensitive_env_name("SESSION_COOKIE")
    assert not is_sensitive_env_name("AGENTENV_MODEL_BASE_URL")
    assert not is_sensitive_env_name("PATH")


def test_scrubbed_subprocess_env_removes_sensitive_values() -> None:
    env = {
        "AGENTENV_MODEL_API_KEY": CANARY,
        "HF_TOKEN": CANARY,
        "PATH": "/usr/bin",
        "AGENTENV_MODEL_BASE_URL": "https://provider.test/v1",
    }

    scrubbed = scrubbed_subprocess_env(env)

    assert "AGENTENV_MODEL_API_KEY" not in scrubbed
    assert "HF_TOKEN" not in scrubbed
    assert scrubbed["PATH"] == "/usr/bin"
    assert scrubbed["AGENTENV_MODEL_BASE_URL"] == "https://provider.test/v1"


def test_redact_secrets_redacts_env_values_and_token_shapes() -> None:
    text = (
        f"env={CANARY} bearer=Bearer {CANARY} "
        "openai=sk-thisisasynthetictesttoken"
    )

    redacted = redact_secrets(text, env={"AGENTENV_MODEL_API_KEY": CANARY})

    assert CANARY not in redacted
    assert "sk-thisisasynthetictesttoken" not in redacted
    assert redacted.count(REDACTED_SECRET) >= 2


def test_redact_jsonable_recurses_without_redacting_field_names() -> None:
    redacted = redact_jsonable(
        {
            "api_key_env": "AGENTENV_MODEL_API_KEY",
            "nested": [f"leaked {CANARY}"],
            CANARY: "secret key",
        },
        env={"AGENTENV_MODEL_API_KEY": CANARY},
    )

    assert redacted["api_key_env"] == "AGENTENV_MODEL_API_KEY"
    assert redacted["nested"] == [f"leaked {REDACTED_SECRET}"]
    assert redacted[REDACTED_SECRET] == "secret key"
