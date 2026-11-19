# The study

**[Preregistered on OSF](https://osf.io/vycge/overview?view_only=6c0c2ac8fc9f4b92a6b4d6db76538201) on 10 November 2026 (embargoed until the results are published; this view-only link opens it). Results pending.**

The only claim tenure makes about the study: the same rule as a preregistered study, replayed on 6,000+ simulated agents. It does not claim that the study has confirmed the rule.

The middle tier (act, then notify) is part of the study.

Added layers:

- spot checks on a cleared type (one in ten by default);
- the requirement of two distinct sessions;
- suspension after external content.

Trusted start (tenure's default, not the study): a type of the covered kinds (files, memory, subagents, known local
dev tools) asks nothing until its first fault, earns nothing meanwhile, and from that fault on follows the study's rule
from T1. `start: probation` is the study's start.

Adaptations:

- human approval plus clean execution counts as proof, an adaptation of the study's automatic control;
- one trial covers the faults that happen during the wait and the inherited faults;
- evidence is re-based when the stakes of a type change;
- a trial is the next 3 real actions, asked; the study replays 3 hidden variants of the faulty case.
- rule B/2 (Tenure 1.3), stricter than the study: an act-then-tell success (T2) counts only when the owner marks it
  as seen (`/tenure ok`) within its 24-hour undo window; left unread, it is neutral (`unseen`), because silence is
  not a check (research report "Garantie Tenure et détection humaine", 19/11/2026: with silence counted, about 80 %
  of the series could be unread and the real AOQ about twice the displayed one). The sessions are conversations (a
  subagent's counts as its parent's), at least 2 at low stakes and 3 at medium, and none gives more than half of
  the series: a 51 + 1 split is one context, not two;
- detection is not perfect: an error counts only when it is caught (your refusal, an undo, a flag, a verifier, or
  the automatic parse check). The parse check tolerates what tools accept (JSON with comments in editor and build
  configs, a byte order mark) and never charges the agent for a file that was broken before its call and that no
  call of the session wrote; such a call is neutral (`ambiguous`), so the ledger shows how often it happens.

Field categories are a classification precision: an MCP call is split by the kind of field it touches (`secret`,
`finance`, `unclassified` by default), so a fault on a bank field no longer lands on the tool's plain calls. The
rule itself is applied to the finer types as it is to any type. No success of a tool ever counts for its
categories (the study's pieces 2 and 8), and the guard that makes a faulty tool keep its categories asking reads
only faults not yet redeemed.

Carry-over is our addition; strict mode is the study. The public-benchmark veto is our addition too.

This page will give the results, whatever they are, when the study is published. The README section [The study behind the rule](../README.md#the-study-behind-the-rule) describes the question, the preregistration and the experiment now running.
