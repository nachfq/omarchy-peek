---
{"id":"at-a-glance","title":"Release Peek 0.2.0 with a readable resource overview","status":"done","depends_on":["mvp"]}
---

# Peek at a glance

## Specs

- **S1 Overview:** Default opening shows compact Docker disk categories/running
  count, running user/system services and worktree count/largest measured sizes.
  Label every metric; unavailable is never zero, incomplete sizes are lower bounds,
  independent filesystem measurements must not be added into a misleading total.
- **S2 Readability:** Primary metrics and useful rows come before diagnostics.
  Use readable sizes, clear visual hierarchy, a legible solid theme background,
  compact rows, size ordering where meaningful and responsive layout.
- **S3 Progressive detail:** Section views preserve all factual data, filtering
  and timestamps. Services start with running user services; user/system/all and
  all-state views remain accessible. Diagnostics and accounting notes are collapsed,
  with a small visible incomplete/unavailable indicator and an explicit way to open
  details. Fatal errors have a concise clear state and manual retry.
- **S4 Correctness:** Fix unmeasured worktree/disk rows shown as zero and preserve
  completed worktree rows across deadlines. Expose table coverage so empty and
  unavailable summaries cannot be confused. No claimed agent attribution.
- **S5 Lifecycle:** No polling, cleanup or inference. Overview starts a bounded
  sequence of Docker/services/worktrees requests on open/Refresh, shows results
  incrementally and cancels on close or section switch. No overlapping requests,
  stale updates or surviving helper children. Detail views still collect only their
  requested section. Manual refresh is the only recurring collection trigger.
- **S6 Delivery:** Independent review, tests with representative synthetic data,
  rendered previews at scales 1 and 1.5, real integration, passing CI, v0.2.0 release
  and update of the installed user plugin while preserving its settings/placement.

## Technical approach

Version 0.1.0 renders every backend note before generic raw tables. Actual local
inspection found working Docker/services data buried under notes and 416 registered
services although only 56 were running. A shared filesystem budget also produced
many 0-byte rows without any scan. The revision separates an overview, resource
lists and expandable diagnostics, while correcting the misleading measurements.

The existing five-section protocol remains version 1. Tables gain optional
`status` (ok/partial/error), with missing status falling back conservatively to the
snapshot status. Backend output retains original string cells and all notes.
Measurements use complete/partial/unavailable; no observation means unavailable
bytes, not numeric zero. Worktree rows gain entries where useful for coverage.
No new CPU/RAM collection or aggregate filesystem-total claim is required here.
A measured benchmark justified optional bounded GNU du size collection: it finishes
large paths that the Python entry cap truncates. Its command time/output budget
and global deadline remain enforced; Python remains the bounded fallback.

Overview is a QML-only request sequence over existing collectors (Docker,
services, worktrees), with per-result timestamps and loading states. Section
indices 0..4 remain stable; -1 denotes Overview. UI code owns sequencing and
presentation; backend owns measurement and coverage truth. No inference labels
resources as belonging to an agent. User services is an observable scope.

## Tasks

- **T1** (S1–S4), done, coordinator: inspect real UI/source and five collectors;
  record this plan and shared contract. Confirmed routine notes dominate results,
  excessive inactive service rows, and unmeasured filesystem rows shown as zero.
- **T2** (S4), done, backend implementer: table coverage, truthful unmeasured
  sizes, deadline preservation, targeted regressions. Files scripts/peek.py and
  tests/test_collectors.py. Completed: 40 tests pass, including nine regressions
  for coverage, unavailable sizes, preserved deadline results and bounded native
  scanning. Real five-section smoke verified improved size coverage without false
  zeros. Partial results retain explicit bounds; no private snapshots enter Git.
- **T3** (S1–S3,S5), done, UI implementer: Overview, compact metrics/resource
  views, readable sizes, filters and expandable diagnostics; request lifecycle and
  representative UI tests/previews. Own QML/Model.js, tests/ui, scripts/test_ui.py,
  scripts/check_qml.sh. Completed: 21 UI checks at scales 1 and 1.5,
  39 requests per default run, no overlap or surviving fixture children.
  Overview, Services and Worktrees previews inspected; real-data Overview checked
  in an isolated private rendering. Pinned QML/manifest validation passes.
- **T4** (S6), done, coordinator, depends T2,T3: integrate, inspect rendered
  real/synthetic results, verify integration, update docs/version and independent
  review. Publish PR/release and update installed plugin.
  Integration evidence: real Overview plus all five sections and cancellation pass
  offscreen and on native Wayland, including focus, placement and Escape.
  Independent full review found no actionable functional defects. Its first scale
  1.5 UI run failed once in notes/filter input; its repeat passed. The test helper
  now waits for scheduled window layout before clicking; targeted verification
  and the single focused review follow-up cover this synchronization change.
  Final helper checks: scale 1 passed in focused independent review; scale 1.5
  passed locally. No production files changed after the full review. The original
  intermittent failure cause was not proven.
  Published through PR #3 after both GitHub Checks runs passed (collectors and
  QML/native UI/integration). Release v0.2.0 targets the exact merged commit
  `babd77c1eeb0215f285654c5546bf316a29f7cd5`; a fresh public clone matched that
  SHA and passed official manifest validation. The release is public, stable and
  latest: https://github.com/nachfq/omarchy-peek/releases/tag/v0.2.0.
  Installed plugin updated to the release SHA, clean, enabled beside Yuragi with
  unchanged Peek settings. Plugin rescan retained the old in-memory QML; a shell
  restart loaded the new Overview, verified visually on the actual desktop.
  Private desktop captures remain outside Git. The update troubleshooting note
  records this observed reload requirement. No packaged Omarchy files changed.

## Delivery outcome

The authorized UI/UX iteration is released and installed. No implementation tasks
remain in this delivery. Filesystem measurements retain explicit scope/coverage
limits; no background polling, cleanup, inference or agent attribution was added.
Future design feedback belongs to a separate bounded iteration.
