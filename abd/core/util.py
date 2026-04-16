def unwrap[T](var: T | None) -> T:
    """ Unwrap an optional value, throwing if it's None. """
    if var is None:
        raise ValueError("Expected value, got None")
    return var
