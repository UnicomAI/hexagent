"""Framework-agnostic task tools.

These tools operate against a :class:`~clawwork.tasks.TaskRegistry`
and are assembled by the agent factory.
"""

from clawwork.tools.task.agent import AgentTool
from clawwork.tools.task.output import TaskOutputTool
from clawwork.tools.task.stop import TaskStopTool

__all__ = [
    "AgentTool",
    "TaskOutputTool",
    "TaskStopTool",
]
