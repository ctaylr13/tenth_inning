import re

def looks_like_identifier(key: str):
    """
    Returns True if a key resembles a primary ID rather than a schema field
    """
    if len(key) > 20:
        return False

    digit_ratio = sum(c.isdigit() for c in key) / len(key)

    return (
        digit_ratio > 0.3      # mostly numbers
        or re.match(r"^[A-Z]*\d+$", key)   # ID12345, ABC123
        or re.match(r"^\d+$", key)         # pure numeric
    )


def is_object_map(d):
    if not isinstance(d, dict) or len(d) < 2:
        return False

    keys = list(d.keys())

    # If majority of keys look like identifiers → collapse
    id_like = sum(looks_like_identifier(k) for k in keys)

    if id_like / len(keys) < 0.6:
        return False

    # values must be objects
    if not all(isinstance(v, dict) for v in d.values()):
        return False

    return True