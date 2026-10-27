import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory


class UnavailableAPI:
    """Temporarily mask a request FIFO without disturbing live result pipes."""

    def __init__(self, api_exec_node_directory, api_root):
        self.request_pipe = Path(api_exec_node_directory) / "exec"
        self.api_root = api_root

    def __enter__(self):
        if not stat.S_ISFIFO(self.request_pipe.stat().st_mode):
            raise ValueError(f"Not a request FIFO: {self.request_pipe}")
        # Stay on the shared filesystem, outside the domain traversed by discovery.
        self.backup = TemporaryDirectory(prefix=".unavailable-", dir=self.api_root)
        self.saved_pipe = Path(self.backup.name) / "exec"
        try:
            os.link(self.request_pipe, self.saved_pipe)
            # An empty regular file keeps the endpoint invalid and prevents
            # generated servers from recreating its request FIFO with mkfifo.
            mask = Path(self.backup.name) / "mask"
            mask.touch()
            os.replace(mask, self.request_pipe)
        except BaseException:
            if self.saved_pipe.exists():
                os.replace(self.saved_pipe, self.request_pipe)
            self.backup.cleanup()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        os.replace(self.saved_pipe, self.request_pipe)
        self.backup.cleanup()
