# Conversation Permanent Deletion Design

## Goal

Allow users to permanently delete one conversation or all conversations from
the recent-conversation sidebar. Deletion removes the case, analyses, events,
idempotency records, messages, clarification state, and original image files.

## User Experience

- Each history row has a delete button that is separate from the navigation
  link.
- The recent-conversation header has a clear-all action when records exist.
- Both actions require explicit confirmation and state that screenshots and
  analysis history will be permanently removed.
- While deletion is running, destructive actions are disabled.
- A failed request leaves the visible history unchanged and shows an inline
  error.
- Deleting the active conversation redirects to `/`.
- Deleting a non-active conversation updates the sidebar in place.

## API

- `DELETE /v1/cases/{case_id}` permanently deletes one case.
- `DELETE /v1/cases` permanently deletes every case.
- Both operations are idempotent and return a JSON deletion count.
- Browser-facing Next.js routes enforce same-origin requests and proxy the
  API token without exposing it to the browser.

## Persistence And Files

`CaseRepository` deletes `analyses`, `case_events`, `idempotency_keys`, and
`cases` in one database transaction. Before the transaction, the API moves
each case image directory into a private trash directory below the configured
image root. If the database transaction fails, the image directory is moved
back. After commit, the trash directory is removed permanently.

Paths are resolved and verified to remain below the configured image root.
The implementation derives the directory from the validated case ID rather
than trusting paths stored in event payloads.

## Testing

- Repository tests cover complete related-record deletion and idempotency.
- API tests cover single deletion, bulk deletion, image removal, missing
  cases, and rollback restoration.
- Proxy tests cover same-origin enforcement and upstream relay.
- Playwright tests cover cancel, single delete, active-case redirect,
  clear-all, loading state, and error preservation.
