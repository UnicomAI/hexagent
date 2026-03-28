"""Local computer implementations."""

import sys

from clawwork.computer.local.native import LocalNativeComputer

if sys.platform == "win32":
    from clawwork.computer.local.vm_win import LocalVM
else:
    from clawwork.computer.local.vm import LocalVM

__all__ = ["LocalNativeComputer", "LocalVM"]
