import signal
import subprocess
import sys


processes: list[subprocess.Popen] = []


def terminate_children(signum, _frame) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()

    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    sys.exit(128 + signum)


def main() -> None:
    commands = [
        ["python", "/app/packages/lazycat-markitdown-web/markitdown_web.py", "--host", "0.0.0.0", "--port", "3000"],
        ["python", "/app/packages/lazycat-markitdown-web/markitdown_mcp.py", "--http", "--host", "0.0.0.0", "--port", "3001"],
    ]

    signal.signal(signal.SIGTERM, terminate_children)
    signal.signal(signal.SIGINT, terminate_children)

    for command in commands:
        processes.append(subprocess.Popen(command))

    exit_code = 0

    try:
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    exit_code = return_code
                    raise SystemExit(return_code)
            signal.pause()
    except SystemExit:
        for process in processes:
            if process.poll() is None:
                process.terminate()

        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

        sys.exit(exit_code)


if __name__ == "__main__":
    main()
