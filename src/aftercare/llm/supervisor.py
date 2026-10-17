"""Hard wall-clock deadline and cancellation, independent of SDK timeout cooperation."""

import multiprocessing as mp
import time


def _child(function, args, pipe):
    try:
        pipe.send(("ok", function(*args)))
    except BaseException as e:
        pipe.send(("error", type(e).__name__))
    finally:
        pipe.close()


def bounded(function, args=(), seconds=180, cancel=None):
    context = mp.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(function, args, child))
    process.start()
    child.close()
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                raise TimeoutError("TASK_CANCELLED")
            if parent.poll(min(0.05, max(0, deadline - time.monotonic()))):
                status, result = parent.recv()
                if status == "error":
                    raise RuntimeError(result)
                return result
            if not process.is_alive():
                raise RuntimeError("CHILD_EXITED")
        raise TimeoutError("TASK_DEADLINE_EXCEEDED")
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.5)
            if process.is_alive():
                process.kill()
        process.join(timeout=2)
        parent.close()
