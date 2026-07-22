from config_types import ConfigFragment, ServiceConfig


def empty_fragment() -> ConfigFragment:
    return ConfigFragment(service={}, limits={}, labels={})


def merge_fragments(base: ConfigFragment, override: ConfigFragment) -> ConfigFragment:
    service = dict(base.service)
    limits = dict(base.limits)
    labels = dict(base.labels)
    if override.service:
        service = dict(override.service)
    if override.limits:
        limits = dict(override.limits)
    if override.labels:
        labels = dict(override.labels)
    return ConfigFragment(service=service, limits=limits, labels=labels)


def finalize_config(fragment: ConfigFragment) -> ServiceConfig:
    return ServiceConfig(
        host=str(fragment.service.get("host", "localhost")),
        port=int(fragment.service.get("port", 8080)),
        timeout_seconds=float(fragment.limits.get("timeout_seconds", 30.0)),
        retries=int(fragment.limits.get("retries", 3)),
        labels=dict(fragment.labels),
    )
