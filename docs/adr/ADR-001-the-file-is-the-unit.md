# ADR-001: the file is the unit, and the plan estimate has no field for it

## Status

Accepted. Everything else in the repository follows from it.

## Context

The natural way to describe a table for a cost model is by its totals: bytes,
rows, partitions. That is what every engine's statistics carry, what every plan
prints, and what every capacity model a team writes down uses.

It is also exactly the description that cannot express the problem. Two tables
with identical totals can differ by an order of magnitude in scan time, and no
function of those totals can tell them apart, because the quantity that
separates them is the file count and the file count is not among them.

## Decision

A `Layout` is a tuple of `DataFile`, each with its own byte count, row count and
partition. No averages, no summary statistics in the stored form. Everything
derived is a property computed from the files, so a layout cannot drift out of
agreement with its own summary.

`PlanEstimate` is a separate frozen type holding exactly three integers: bytes,
rows, partitions. It has no reference to the layout it came from and no field
for the file count.

That second decision is the one doing the work. The claim "a plan cannot tell
these apart" is checkable rather than rhetorical, because the type a plan is
modelled as has no field to cheat with, and two estimates compare equal by
construction when their three numbers match.

## Consequences

The shipped `events` layout is sixteen thousand `DataFile` objects. That is more
memory than a summary would use and it is still nothing, and it means a reader
can inspect any individual file rather than taking a distribution on trust.

`Layout` exposes both `mean_file_bytes` and `median_file_bytes` and the tests
pin the case where they disagree, because the mean is what a monitoring
dashboard reports and the median is what the scan time agrees with. A table with
one large file and four hundred small ones has a mean in the megabytes and a
median of 64 KiB.

The cost: the model cannot describe a table it cannot enumerate. A real
hundred-million-file table would not fit, and the honest version of this
repository at that scale would sample. ADR-003 records that as a limit rather
than pretending the approach generalises.

## Alternatives considered

**A distribution instead of a list.** A file-size histogram would hold the same
information for a tenth of the memory, and it would also let a summary and a
layout disagree, which is precisely the failure mode under study. Rejected on
the grounds that a repository about a model that cannot see something should not
build its own model that cannot see something.

**Giving `PlanEstimate` the file count and ignoring it.** Rejected: an ignored
field is one refactor away from being used, and the claim would quietly stop
being checkable.
