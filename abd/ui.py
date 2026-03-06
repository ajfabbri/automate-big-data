# from rich.console import Console


class Ui:
    def __init__(self):
        # TODO basic and rich UI modes
        # for now, do basic text
        # make rich output optional?
        # self.console = Console(color_system='256')
        pass

    def prompt_bool(self, prompt, default):
        val = input(f"{prompt} [{default}]: ").strip().lower()
        if val == '':
            return default
        return val in ('y', 'yes', 'true', '1')

    def prompt_int(self, prompt, default):
        val = input(f"{prompt} [{default}]: ").strip()
        if val == '':
            return default
        try:
            return int(val)
        except ValueError:
            return default

    def prompt_str(self, prompt, default):
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
