"""Local computer implementations."""

import sys

from openagent.computer.local.native import LocalNativeComputer

if sys.platform == "win32":
    from openagent.computer.local.vm_win import LocalVM
else:
    from openagent.computer.local.vm import LocalVM

__all__ = ["LocalNativeComputer", "LocalVM"]
