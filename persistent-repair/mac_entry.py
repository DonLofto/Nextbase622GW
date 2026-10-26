"""Bundled Mac console entrypoint and read-only passive capture worker."""
import sys
import capture_rtos
from repair import interactive_console, main


def run(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--passive-reader"]:
        return capture_rtos.main(argv[1:])
    result = main(argv)
    if interactive_console():
        try:
            input("Press Return to close. ")
        except (EOFError, KeyboardInterrupt):
            pass
    return result


if __name__ == "__main__":
    raise SystemExit(run())
