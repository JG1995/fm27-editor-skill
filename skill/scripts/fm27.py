"""Read and write Football Manager 27 editor files. Run with --help for the commands."""

import sys

# The check is for whichever python3 runs this, which need not be the one it was written for.
if sys.version_info < (3, 14):  # noqa: UP036
    sys.exit("error: Python 3.14 or newer is needed")
try:
    from fm27_editor.command_line import main
except ModuleNotFoundError as error:
    sys.exit(f"error: {error.name} is missing; run python3 -m pip install cryptography numpy")

sys.exit(main(sys.argv[1:]))
