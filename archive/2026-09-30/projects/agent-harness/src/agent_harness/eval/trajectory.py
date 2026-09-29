"""Compatibility exports for trajectory persistence.

The first capstone draft kept trajectories in ``suite.py``.  This module makes
the natural ``agent_harness.eval.trajectory`` import available without
maintaining a second implementation.
"""

from agent_harness.eval.suite import Trajectory, TrajectoryStore

__all__ = ["Trajectory", "TrajectoryStore"]
