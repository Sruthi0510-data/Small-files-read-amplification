"""Measures the part of a scan's cost that a query plan structurally cannot report.

A plan tells you bytes scanned and rows scanned. Both are properties of the
data. The cost that actually dominates a badly laid out table is paid per file,
for opening it, and it is a property of the reader. The plan does not have it
and could not get it, so two layouts the plan calls identical can differ by an
order of magnitude in wall time with nothing anywhere to say so.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
