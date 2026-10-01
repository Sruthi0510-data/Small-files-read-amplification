# ADR-003: what this repository cannot measure

## Status

Accepted. This file exists so nobody has to guess whether an omission was an
oversight.

## Caching is not modelled, and it is the big one

Every layer in the stack caches. The object store caches, the engine caches file
handles and footers, the operating system caches pages, and a cluster that reads
the same table every hour pays the per-file cost once and then does not.

A warm read of this table would be far cheaper than the model says, and the
model has nothing to say about how much. That is the mechanism most likely to
make a reader's real numbers differ from these, and it points one way: the
per-file cost is paid in full on a cold read and partially or not at all on a
warm one.

What survives is the comparison between layouts, because caching helps both, and
the break-even size, which moves down with caching but does not reach zero.

## Compression and encoding are not modelled

A Parquet file's scan cost depends on its compression codec, its encodings, its
row group size and which columns are projected. All of that is folded into a
single throughput number here. Column pruning in particular is a real and large
optimisation that this model cannot express, and it is one that reduces bytes
without reducing the file count, which is the pattern that makes plan-reported
improvements overstate real ones.

## Task skew and tail latency are not modelled

Both cost terms are divided flatly by the reader count. ADR-002 records why and
what it is wrong about: a handful of enormous files on many readers, where one
slow task holds up the stage and a flat split understates the time.

## Metadata and listing costs are not modelled

Before a scan reads a file it has to find it. On a Hive-style table that is a
directory listing whose cost grows with the file count; on Delta or Iceberg it
is a metadata read whose cost grows with the number of manifest entries. Both
scale with the same quantity this repository is about, so including them would
make the effect larger, and they are left out in the conservative direction.

## Writes, commits and concurrency are not modelled

A compaction here costs one read plus one write. A real one also writes a commit,
may conflict with concurrent writers, and on some table formats rewrites
metadata proportional to the file count. The payback numbers are therefore
optimistic about the fix.

## The layout must be enumerable

A `Layout` holds every file. That is fine for sixteen thousand and impossible
for a hundred million, and the honest version of this repository at that scale
would sample files and carry the sampling error through every figure. ADR-001
records the decision; this records the limit it implies.

## The storage profiles are claims nobody here can check

Four numbers per profile, carried with a note saying where they come from. No
test verifies them against any cluster, because verifying them needs the
cluster. A reader whose numbers differ should change them: the conclusions are
shaped by the formula, not by the values.

## One table, built rather than sampled

Every figure is measured on one synthetic layout whose shape was chosen to be
typical of a streaming writer plus a nightly compaction job that is behind. It
is not a survey of real tables, and the README quotes it as a demonstration
rather than as a distribution.
