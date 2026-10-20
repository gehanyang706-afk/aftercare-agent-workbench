"""Explicit IPC barriers; only a dedicated test database may install these hooks."""

import os
import subprocess
import time
from dataclasses import dataclass


def process_birth(pid):
    return subprocess.check_output(["ps", "-p", str(pid), "-o", "lstart="], text=True).strip()


@dataclass
class Probe:
    point: str
    channel: object

    def hit(self, point, **payload):
        points = self.point if isinstance(self.point, tuple) else (self.point,)
        if point not in points:
            return
        self.channel.send(
            {
                "point": point,
                "pid": os.getpid(),
                "ppid": os.getppid(),
                "process_started_at": process_birth(os.getpid()),
                "monotonic": time.monotonic(),
                **payload,
            }
        )
        if not self.channel.poll(60):
            raise TimeoutError("RELIABILITY_BARRIER_RELEASE_TIMEOUT")
        if self.channel.recv() != "release":
            raise ValueError("INVALID_BARRIER_RELEASE")
