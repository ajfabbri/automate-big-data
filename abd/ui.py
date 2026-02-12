def prompt_bool(prompt, default):
    val = input(f"{prompt} [{default}]: ").strip().lower()
    if val == '':
        return default
    return val in ('y', 'yes', 'true', '1')


def prompt_int(prompt, default):
    val = input(f"{prompt} [{default}]: ").strip()
    if val == '':
        return default
    try:
        return int(val)
    except ValueError:
        return default


def prompt_str(prompt, default):
    val = input(f"{prompt} [{default}]: ").strip()
    return val if val else default
