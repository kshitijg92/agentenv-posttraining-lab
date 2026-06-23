# Docker Smoke

## Summary

- Status: PASS
- Config: /home/kshitij/agentenv-posttraining-lab/configs/sandbox/docker_none.yaml
- Image: busybox:1.36
- Image digest: busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662
- Network: none

## Probes

| probe | expected | returncode | timed_out | result |
| --- | --- | --- | --- | --- |
| startup | returncode == 0 | 0 | False | PASS |
| network_probe | returncode != 0 under --network none | 1 | False | PASS |

## Limitation

This is a Docker smoke check only. It does not prove production-grade hostile-code sandboxing.
