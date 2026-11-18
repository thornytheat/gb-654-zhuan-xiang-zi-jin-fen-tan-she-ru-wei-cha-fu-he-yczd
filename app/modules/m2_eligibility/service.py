from app import rulebook

from . import core


def execute(payload: dict | None = None, rule_version: str | None = None) -> dict:
    data = dict(payload or {})
    if not data.get("rule_version"):
        data["rule_version"] = rule_version or rulebook.current_version()
    return core.run(data)
