import json
import subprocess
from pathlib import Path

from agentenv.sandbox import docker_smoke
from agentenv.sandbox.docker_smoke import run_docker_smoke


def test_run_docker_smoke_writes_result_and_report(
    monkeypatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(
                command,
                0,
                '["busybox@sha256:0123456789abcdef"]\n',
                "",
            )
        if command[-1] == "echo docker_smoke_ok":
            return subprocess.CompletedProcess(command, 0, "docker_smoke_ok\n", "")
        return subprocess.CompletedProcess(command, 1, "", "bad address\n")

    monkeypatch.setattr(docker_smoke.subprocess, "run", fake_run)

    config_path = tmp_path / "docker_none.yaml"
    config_path.write_text(
        """image: busybox:1.36
network: none
timeout_seconds: 15
startup_command:
  - sh
  - -c
  - echo docker_smoke_ok
network_probe_command:
  - sh
  - -c
  - wget -q -T 2 -O - https://example.com
"""
    )

    result = run_docker_smoke(config_path, tmp_path / "out")

    assert result.status == "PASS"
    assert result.image_digest == "busybox@sha256:0123456789abcdef"
    assert all(
        command[:5] == ["docker", "run", "--rm", "--network", "none"]
        for command in commands
        if command[:3] != ["docker", "image", "inspect"]
    )
    result_json = json.loads((tmp_path / "out/docker_smoke_result.json").read_text())
    assert result_json["image_digest"] == "busybox@sha256:0123456789abcdef"
    assert result_json["image_digest_error"] is None
    report = (tmp_path / "out/docker_smoke.md").read_text()
    assert "# Docker Smoke" in report
    assert "- Image digest: busybox@sha256:0123456789abcdef" in report
    assert "| startup | returncode == 0 | 0 | False | PASS |" in report
    assert (
        "| network_probe | returncode != 0 under --network none | "
        "1 | False | PASS |"
    ) in report
