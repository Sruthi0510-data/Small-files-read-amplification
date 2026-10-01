# ADR-002: a model with its parameters on the page, not a benchmark

## Status

Accepted, with the cost stated plainly.

## Context

There are two ways to make this argument. Run real queries against real storage
and time them, or model the cost and show the model.

A benchmark is more convincing right up until somebody asks a question about it.
Which region, which instance type, what else was running, was the data cached,
how many runs, which percentile. Every one of those is a real question and every
honest answer narrows what the benchmark showed. It also cannot be re-run by a
reader without an account, a cluster and a bill, which means in practice it is
re-run by nobody.

## Decision

A model, with four numbers per storage profile written down where anyone can
disagree with them: the cost to open a file, the footer size, the parse cost and
the throughput. Plus the reader count, which divides both terms.

Every profile carries a `note` saying what its numbers are and what they are
not: order-of-magnitude figures for a cold read on a typical deployment. No test
checks them, because no test can.

Two deliberate conservatisms, both in the direction that weakens this
repository's own argument. The footer read is charged at full throughput rather
than as a separate round trip, which understates the per-file cost on object
storage where it is usually its own request. And a compaction's rewrite is
charged as one read plus one write at read throughput, which understates the
cost of the fix.

## Consequences

The argument does not depend on the parameter values. It depends on the per-file
cost being nonzero, which it is on every storage system that exists, and the
break-even formula is `per-file cost x throughput` regardless of what those are.
A reader who thinks the open cost should be 5 ms rather than 28 can change one
number and re-run, and the shape of every conclusion survives.

The magnitudes do depend on them, and the README says so wherever a magnitude
appears. "86.2% of the modelled scan" is a sentence about a model.

The second cost is the work-splitting rule. Both terms are divided flatly by the
reader count, which approaches what a scheduler with a work queue does when
files outnumber readers. It is wrong for the opposite case, a handful of
enormous files on many readers, where the tail task dominates and a flat split
understates the time. The repository does not model that case and does not claim
to, because the layouts it is about have more files than any cluster has
readers.

## Alternatives considered

**A real benchmark.** Rejected on reproducibility. A result a reader cannot
re-run is a result they have to take on faith, and the whole point of this
repository is that the thing everybody takes on faith, the plan's cost estimate,
is incomplete.

**Both.** The right answer for a production investigation and overkill here. A
benchmark would need to be re-run whenever a cloud provider changed anything,
and a stale benchmark is worse than a model that says it is a model.

**Modelling tail latency and task skew.** Rejected on scope. It would add a
distribution to every profile and a scheduler to the model, and it would change
the magnitudes without touching the argument.
