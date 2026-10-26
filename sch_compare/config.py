import copy
import json

DEFAULTS = {
    "before_name": None,
    "after_name": None,
    "exclude_prefixes": ["T", "TP"],
    "no_value_prefixes": ["T", "TP", "NP", "AA"],
    "value_overrides": {"before": {}, "after": {}},
    "block_names": {"before": {}, "after": {}},
    "block_pairs": [],
    "block_remarks": {},
    "auto_remarks": True,
    "check_items": [],
    "pins": [],
}


def load(path=None):
    cfg = copy.deepcopy(DEFAULTS)
    if not path:
        return cfg
    with open(path, encoding="utf-8") as f:
        user = json.load(f)
    unknown = set(user) - set(DEFAULTS) - {"_comment"}
    if unknown:
        raise ValueError(f"unknown config keys: {', '.join(sorted(unknown))}")
    for k, v in user.items():
        if k == "_comment":
            continue
        if isinstance(DEFAULTS[k], dict) and isinstance(v, dict) and set(DEFAULTS[k]) == {"before", "after"}:
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg
