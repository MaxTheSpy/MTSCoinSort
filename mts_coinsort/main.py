from .wiring import load_and_wire
import sys


def main():
    modules = load_and_wire()
    if any(arg.lower() in ("--terminal", "-t", "terminal") for arg in sys.argv[1:]):
        return modules["terminal_ui"].main()
    from . import gui_ui
    return gui_ui.main()


if __name__ == "__main__":
    main()