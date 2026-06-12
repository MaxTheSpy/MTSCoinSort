# Runtime wiring for the phase-1 modular split.
# This keeps existing function bodies working while files are separated.
import importlib

MODULE_NAMES = ['utils', 'sound', 'settings', 'numista', 'storage', 'statistics', 'sorting', 'terminal_ui']

def load_and_wire():
    modules = [importlib.import_module(f"mts_coinsort.{name}") for name in MODULE_NAMES]
    public = {}
    for module in modules:
        for name, value in module.__dict__.items():
            if callable(value) and not name.startswith("__"):
                public[name] = value
    # Make functions visible to every split module, preserving the original single-file behavior.
    for module in modules:
        module.__dict__.update(public)
    return {module.__name__.rsplit('.', 1)[-1]: module for module in modules}
