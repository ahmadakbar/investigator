"""JSON converter for final report."""
import dataclasses
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, Mapping, get_args, get_origin, get_type_hints


def to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "to_json_dict"):
        return to_jsonable(obj.to_json_dict())

    # NamedTuple (check before plain tuple)
    if isinstance(obj, tuple) and hasattr(obj, "_fields"):
        return _fields_to_jsonable(obj, obj._asdict().items())

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _fields_to_jsonable(
            obj, ((f.name, getattr(obj, f.name)) for f in dataclasses.fields(obj))
        )

    if isinstance(obj, Enum):
        return to_jsonable(obj.value)
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()

    if isinstance(obj, dict):
        if all(isinstance(k, str) for k in obj):
            # Plain object; key order is fixed by sort_keys=True when dumping
            return {k: to_jsonable(v) for k, v in obj.items()}
        return _entries(obj)

    if isinstance(obj, (set, frozenset)):
        return sorted((to_jsonable(v) for v in obj), key=_canonical)

    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]  # sequences keep their order

    return obj


def _entries(mapping: Mapping[Any, Any]) -> list[dict[str, Any]]:
    """Convert a mapping with non-string keys to a sorted, lossless entry list."""
    entries = [{"key": to_jsonable(k), "value": to_jsonable(v)} for k, v in mapping.items()]
    return sorted(entries, key=lambda e: _canonical(e["key"]))


def _fields_to_jsonable(obj: Any, items: Any) -> dict[str, Any]:
    """Convert named fields, using declared types to keep mapping shapes stable.

    A field declared as a mapping with non-string keys (e.g.
    ``dict[tuple[str, ...], Decimal]``) is always an entry list, so an empty
    value becomes ``[]`` rather than ``{}``.
    """
    entry_fields = _entry_list_fields(type(obj))
    return {
        name: _entries(value)
        if name in entry_fields and isinstance(value, Mapping)
        else to_jsonable(value)
        for name, value in items
    }


@cache
def _entry_list_fields(cls: type) -> frozenset[str]:
    """Return names of fields declared as mappings whose keys are not ``str``."""
    try:
        hints = get_type_hints(cls)
    except Exception:
        return frozenset()
    return frozenset(name for name, tp in hints.items() if _has_non_str_keys(tp))


def _has_non_str_keys(tp: Any) -> bool:
    origin = get_origin(tp)
    if not (isinstance(origin, type) and issubclass(origin, Mapping)):
        return False
    args = get_args(tp)
    if not args:
        return False
    key = get_origin(args[0]) or args[0]
    return not (isinstance(key, type) and issubclass(key, str))


def _canonical(value: Any) -> str:
    """Total, type-safe ordering for already-converted JSON values."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _dumps(obj: Any, **kwargs: Any) -> str:
    kwargs.setdefault("indent", 2)
    return json.dumps(to_jsonable(obj), sort_keys=True, ensure_ascii=False, **kwargs)


def write_json(obj: Any, path: str | Path) -> None:
    Path(path).write_text(_dumps(obj) + "\n", encoding="utf-8")