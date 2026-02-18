from rich.console import Console
from abd.sysinfo import Sysinfo


class App:
    """ Application-level context. """
    def __init__(self):
        sysinfo = Sysinfo()
        if sysinfo.load() != 0:
            raise Exception("Failed to load system info.")
        self.sysinfo = sysinfo
        # TODO make rich output optional?
        self.console = Console(color_system='256')
        self.container_network = "abd-network"
