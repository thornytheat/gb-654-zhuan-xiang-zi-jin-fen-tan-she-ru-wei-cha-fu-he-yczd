from . import core


def execute(payload: dict | None = None, store=None) -> dict:
    data = dict(payload or core.SAMPLE)
    if store is not None:
        data["store"] = store
    return core.run(data)


def sign(payload: dict | None = None, store=None) -> dict:
    data = dict(payload or {})
    if store is not None:
        data["store"] = store
    return core.sign(store or data.get("store"), data)


def recheck(store, batch_key: str) -> dict:
    return core.recheck(store, batch_key)
