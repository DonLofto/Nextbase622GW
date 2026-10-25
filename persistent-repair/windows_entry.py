"""Console entrypoint for the portable Windows executable."""
from repair import interactive_console, main


def run():
    result = main()
    if interactive_console():
        try:
            input("Press Return to close. ")
        except (EOFError, KeyboardInterrupt):
            pass
    return result


if __name__ == "__main__":
    raise SystemExit(run())
