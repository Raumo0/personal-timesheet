## Why

The catalog can archive Clients, Projects, and Tasks but cannot restore them,
and ancestor archive currently leaves active descendants in an ambiguous hidden
state. A coherent hierarchy lifecycle is required before weekly time entry can
reliably decide which work is selectable or editable.

## What Changes

- Archive a Project together with all of its Tasks, and archive a Client
  together with all of its Projects and Tasks.
- Restore a selected record without restoring its descendants: a Client alone,
  a Project plus an archived Client ancestor when required, or a Task plus only
  its archived Project and Client ancestor path.
- Show archive and restore actions in the existing hierarchical catalog
  context, with confirmations that identify the exact records or complete
  descendant scope affected.
- Perform every cascade archive and target-plus-ancestor restore atomically;
  preserve the prior state and offer Retry when local persistence fails.
- Preserve archived records and their historical time-entry relationships; the
  lifecycle changes status rather than deleting business data.
- Defer weekly Timesheet read-only rows and `Restore to edit` to
  `record-weekly-time-entries`.
- Defer bulk restore, arbitrary descendant selection, permanent deletion, and
  scheduled or effective-date archival.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `client-catalog`: Client archival cascades through Projects and Tasks, and an
  archived Client can be restored without restoring descendants.
- `project-catalog`: Project archival cascades through Tasks, and an archived
  Project can be restored with only a required Client ancestor.
- `task-catalog`: Archived Tasks can be restored with only their required
  ancestor path, while unrelated records remain unchanged.

## Impact

- Adds one focused hierarchy-lifecycle interface with pure planning plus
  in-memory and SQLite adapters, and routes existing archive actions through
  that single write seam.
- Extends existing Client, Project, and Task catalog screens, archived views,
  confirmations, hierarchy context, error banners, and Retry behavior.
- Adds an upgrade migration that normalizes descendants already stored beneath
  archived ancestors and extends backup-version compatibility without adding a
  runtime dependency or database table.
- Depends on `manage-tasks-with-inherited-rates` for the Task catalog and task
  persistence.
