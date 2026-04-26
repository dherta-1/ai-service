def serialize_value(value):
    """Serialize value for JSON compatibility"""
    import numpy as np

    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, dict)):
        return value
    return value


def to_dict(obj):
    """Convert Peewee model to dictionary"""
    if obj is None:
        return None
    result = {}
    for key, value in obj.__data__.items():
        result[key] = serialize_value(value)
    return result
