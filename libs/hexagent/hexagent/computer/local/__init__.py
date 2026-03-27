"""Local computer implementations."""

import sys

from hexagent.computer.local.native import LocalNativeComputer

if sys.platform == "win32":
    from hexagent.computer.local.vm_win import LocalVM
else:
    from hexagent.computer.local.vm import LocalVM

__all__ = ["LocalNativeComputer", "LocalVM"]
