import sys
import os

class DummyWriter:
    def write(self, *args, **kwargs):
        pass
    def flush(self, *args, **kwargs):
        pass

# If packaged with --noconsole, standard streams may be None or closed.
# Redirect them to a dummy writer to prevent any print statement from crashing.
if sys.stdout is None or not hasattr(sys.stdout, 'write'):
    sys.stdout = DummyWriter()
if sys.stderr is None or not hasattr(sys.stderr, 'write'):
    sys.stderr = DummyWriter()

def main():
    if len(sys.argv) > 1:
        # CLI Mode
        from spaceweather.cli import main as cli_main
        cli_main()
    else:
        # GUI Mode
        from spaceweather.gui import start_gui
        start_gui()

if __name__ == "__main__":
    main()
