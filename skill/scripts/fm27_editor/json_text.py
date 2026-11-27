"""JSON text in which every name stands once in each place, as a request and its items need.

`json.loads` keeps the last of two values with one name, which would leave a value out unseen.
"""

import json
from typing import Any

from fm27_editor.binary import FormatError


class RepeatedNameError(FormatError):
    """A name is given twice in one place."""


def read_json(text: str) -> Any:
    """The value of the text; `json.JSONDecodeError` if it is not JSON."""
    return json.loads(text, object_pairs_hook=_named_once)


def _named_once(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    names = [name for name, _ in pairs]
    repeated = {name for name in names if names.count(name) > 1}
    if repeated:
        raise RepeatedNameError(f"{', '.join(sorted(repeated))} is given twice in one place")
    return dict(pairs)
