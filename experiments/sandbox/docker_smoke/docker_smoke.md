# Docker Smoke

## Summary

- Status: PASS
- Config: /home/kshitij/agentenv-posttraining-lab/configs/sandbox/docker_none.yaml
- Image: busybox:1.36
- Network: none

## Probes

| probe | expected | returncode | timed_out | result |
| --- | --- | --- | --- | --- |
| startup | returncode == 0 | 0 | False | PASS |
| network_probe | returncode != 0 under --network none | 1 | False | PASS |

## Limitation

This is a Docker smoke check only. It does not prove production-grade hostile-code sandboxing.
