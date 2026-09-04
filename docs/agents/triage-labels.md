# Triage labels

The skills speak in five canonical triage roles. This file maps them onto the labels that exist in this repo's tracker, GitHub Issues on `kitcut-hq/kitcut`.

GitHub has no status field, so every role is a real label.

| Role in mattpocock/skills | Label in this repo | Meaning |
| ------------------------- | ------------------ | ------- |
| `needs-triage` | `needs triage` | Maintainer needs to evaluate this issue |
| `needs-info` | `needs info` | Waiting on reporter for more information |
| `ready-for-agent` | `ready for agent` | Fully specified, ready for an AFK agent |
| `ready-for-human` | `ready for human` | Requires human implementation |
| `wontfix` | `wontfix` | Will not be actioned |

An open issue carries exactly one of these. An AFK agent picks up only `ready for agent`.

## Category labels

| label | meaning |
| ----- | ------- |
| `bug` | Something is broken |
| `feature` | New capability |
| `improvement` | A change to something that already works |

A category label is independent of the triage label; an issue normally has one of each.

## Routing labels

`frontend`, `backend`, `research` - apply when they obviously fit. Never invent a new label without asking.

## Naming

Label names are lowercase, with spaces rather than hyphens. Follow that if a label is ever added.
