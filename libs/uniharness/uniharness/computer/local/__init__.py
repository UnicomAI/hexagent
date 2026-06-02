"""Local computer implementations."""

import sys

from uniharness.computer.local.native import LocalNativeComputer

if sys.platform == "win32":
    from uniharness.computer.local.vm_win import LocalVM
else:
    from uniharness.computer.local.vm import LocalVM

__all__ = ["LocalNativeComputer", "LocalVM"]
