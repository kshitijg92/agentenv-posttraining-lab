import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


DockerNetworkMode = Literal["none"]
DockerSmokeStatus = Literal["PASS", "FAIL"]
DockerProbeName = Literal["startup", "network_probe"]


class DockerSmokeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image: str = Field(min_length=1)
    network: DockerNetworkMode
    timeout_seconds: int = Field(gt=0)
    startup_command: list[str] = Field(min_length=1)
    network_probe_command: list[str] = Field(min_length=1)


@dataclass(frozen=True)
class DockerProbeResult:
    name: DockerProbeName
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str | None = None


@dataclass(frozen=True)
class DockerSmokeResult:
    status: DockerSmokeStatus
    config_path: Path
    out_dir: Path
    config: DockerSmokeConfig
    image_digest: str | None
    image_digest_error: str | None
    probes: tuple[DockerProbeResult, ...]


def load_docker_smoke_config(path: Path) -> DockerSmokeConfig:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected Docker smoke config object at {path}")
    return DockerSmokeConfig.model_validate(raw)


def run_docker_smoke(config_path: Path, out_dir: Path) -> DockerSmokeResult:
    config_path = config_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    config = load_docker_smoke_config(config_path)

    startup = _run_probe("startup", config, config.startup_command)
    network_probe = _run_probe("network_probe", config, config.network_probe_command)
    image_digest, image_digest_error = _inspect_image_digest(config)
    result = DockerSmokeResult(
        status=_smoke_status(startup, network_probe),
        config_path=config_path,
        out_dir=out_dir,
        config=config,
        image_digest=image_digest,
        image_digest_error=image_digest_error,
        probes=(startup, network_probe),
    )
    _write_json(result)
    _write_markdown(result)
    return result


def _run_probe(
    name: DockerProbeName,
    config: DockerSmokeConfig,
    probe_command: list[str],
) -> DockerProbeResult:
    docker_command = [
        "docker",
        "run",
        "--rm",
        "--network",
        config.network,
        config.image,
        *probe_command,
    ]
    try:
        completed = subprocess.run(
            docker_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return DockerProbeResult(
            name=name,
            command=docker_command,
            returncode=None,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            timed_out=True,
            error=f"Timed out after {config.timeout_seconds}s",
        )
    except FileNotFoundError as exc:
        return DockerProbeResult(
            name=name,
            command=docker_command,
            returncode=None,
            stdout="",
            stderr="",
            error=str(exc),
        )

    return DockerProbeResult(
        name=name,
        command=docker_command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _inspect_image_digest(config: DockerSmokeConfig) -> tuple[str | None, str | None]:
    docker_command = [
        "docker",
        "image",
        "inspect",
        config.image,
        "--format",
        "{{json .RepoDigests}}",
    ]
    try:
        completed = subprocess.run(
            docker_command,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None, f"Timed out after {config.timeout_seconds}s"
    except FileNotFoundError as exc:
        return None, str(exc)

    if completed.returncode != 0:
        error = completed.stderr.strip() or completed.stdout.strip()
        return None, error or f"docker image inspect exited {completed.returncode}"

    try:
        repo_digests = json.loads(completed.stdout.strip() or "[]")
    except json.JSONDecodeError as exc:
        return None, f"Could not parse RepoDigests JSON: {exc}"

    if not isinstance(repo_digests, list):
        return None, "RepoDigests was not a JSON list"

    digests = [digest for digest in repo_digests if isinstance(digest, str)]
    if not digests:
        return None, None
    return digests[0], None


def _smoke_status(
    startup: DockerProbeResult,
    network_probe: DockerProbeResult,
) -> DockerSmokeStatus:
    startup_passed = (
        startup.returncode == 0 and not startup.timed_out and startup.error is None
    )
    network_blocked = (
        network_probe.returncode is not None
        and network_probe.returncode != 0
        and not network_probe.timed_out
        and network_probe.error is None
    )
    return "PASS" if startup_passed and network_blocked else "FAIL"


def _write_json(result: DockerSmokeResult) -> Path:
    path = result.out_dir / "docker_smoke_result.json"
    path.write_text(json.dumps(_result_json(result), indent=2, sort_keys=True) + "\n")
    return path


def _write_markdown(result: DockerSmokeResult) -> Path:
    path = result.out_dir / "docker_smoke.md"
    lines = [
        "# Docker Smoke",
        "",
        "## Summary",
        "",
        f"- Status: {result.status}",
        f"- Config: {result.config_path}",
        f"- Image: {result.config.image}",
        f"- Image digest: {result.image_digest or 'unavailable'}",
        f"- Network: {result.config.network}",
        "",
        "## Probes",
        "",
        "| probe | expected | returncode | timed_out | result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for probe in result.probes:
        lines.append(
            f"| {probe.name} | {_probe_expectation(probe.name)} | "
            f"{probe.returncode} | {probe.timed_out} | "
            f"{_probe_match_display(probe)} |"
        )
    lines.extend(
        [
            "",
            "## Limitation",
            "",
            "This is a Docker smoke check only. It does not prove production-grade "
            "hostile-code sandboxing.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")
    return path


def _result_json(result: DockerSmokeResult) -> dict[str, object]:
    return {
        "status": result.status,
        "config_path": str(result.config_path),
        "image": result.config.image,
        "image_digest": result.image_digest,
        "image_digest_error": result.image_digest_error,
        "network": result.config.network,
        "timeout_seconds": result.config.timeout_seconds,
        "artifacts": {
            "result": "docker_smoke_result.json",
            "report": "docker_smoke.md",
        },
        "probes": [
            {
                "name": probe.name,
                "command": probe.command,
                "returncode": probe.returncode,
                "stdout": probe.stdout,
                "stderr": probe.stderr,
                "timed_out": probe.timed_out,
                "error": probe.error,
                "match": _probe_matches_expectation(probe),
            }
            for probe in result.probes
        ],
    }


def _probe_matches_expectation(probe: DockerProbeResult) -> bool:
    if probe.name == "startup":
        return probe.returncode == 0 and not probe.timed_out and probe.error is None
    return (
        probe.returncode is not None
        and probe.returncode != 0
        and not probe.timed_out
        and probe.error is None
    )


def _probe_match_display(probe: DockerProbeResult) -> DockerSmokeStatus:
    return "PASS" if _probe_matches_expectation(probe) else "FAIL"


def _probe_expectation(name: DockerProbeName) -> str:
    if name == "startup":
        return "returncode == 0"
    return "returncode != 0 under --network none"
