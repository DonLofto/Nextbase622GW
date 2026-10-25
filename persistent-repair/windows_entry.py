"""Console entrypoint for the portable Windows executable."""
import sys
from repair import main


def run():
    result = main()
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("Press Return to close. ")
        except (EOFError, KeyboardInterrupt):
            pass
    return result


if __name__ == "__main__":
    raise SystemExit(run())
