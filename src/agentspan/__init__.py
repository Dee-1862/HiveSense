"""HiveDoctor: a selective, durable human-in-the-loop treatment agent on Orkes Agentspan.

It interrupts the beekeeper only when a Value-of-Information calculation (voi.py) says
their judgement is worth more than the cost of asking, and couples that pause to
Agentspan so the question survives a crash. See hive_doctor.py."""

from . import voi, runs, hive_doctor  # noqa: F401
