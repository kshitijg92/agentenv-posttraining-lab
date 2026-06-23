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
    assert all(
        command[:5] == ["docker", "run", "--rm", "--network", "none"]
        for command in commands
    )
    assert (tmp_path / "out/docker_smoke_result.json").is_file()
    report = (tmp_path / "out/docker_smoke.md").read_text()
    assert "# Docker Smoke" in report
    assert "| startup | returncode == 0 | 0 | False | PASS |" in report
    assert (
        "| network_probe | returncode != 0 under --network none | "
        "1 | False | PASS |"
    ) in report
