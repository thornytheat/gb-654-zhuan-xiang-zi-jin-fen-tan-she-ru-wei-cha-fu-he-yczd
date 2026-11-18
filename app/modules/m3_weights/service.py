from . import core

def execute(payload: dict | None = None) -> dict:
    return core.build(payload or core.SAMPLE)
