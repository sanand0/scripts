---
title: qsv
docs: https://github.com/googleworkspace/cli
---

```bash
gws auth status # (token + scope check)
gws calendar +agenda
gws gmail +triage
gws workflow +standup-report
gws workflow +weekly-digest
gws workflow +meeting-prep
gws workflow +email-to-task # (created a task from an email, then deleted it)
gws drive files list # or: `about get`, `+upload`
gws tasks tasklists list` # or: `tasks insert`, `tasks delete`
gws docs documents create` # or: `gws docs +write`
gws sheets spreadsheets create` # or: `gws sheets +append`, `gws sheets +read`
gws slides presentations create` # or: `presentations batchUpdate`
gws calendar freebusy query` # or: `events insert`, `events delete`
gws schema ...` # e.g. gws schema drive.files.list
gws chat spaces list # failed with `403 Request had insufficient authentication scopes (expected with current scopes).

gws drive files list --params '{"pageSize":100}' --page-all --page-limit 5  # Pagination

# `--format json|table|csv|...`, `--dry-run`

gws calendar +agenda # What does my day look like?
gws calendar freebusy query --json '{"timeMin":"2026-03-06T00:00:00Z","timeMax":"2026-03-07T00:00:00Z","items":[{"id":"primary"}]}' # check free-busy time before proposing a meeting
gws calendar events insert --params '{"calendarId":"primary"}' --json '{"summary":"Focus Time","start":{"dateTime":"2026-03-09T09:00:00+08:00"},"end":{"dateTime":"2026-03-09T11:00:00+08:00"},"recurrence":["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"],"transparency":"opaque"}' # block recurring focus time

gws gmail +triage # What's urgent in inbox?
gws gmail users messages list --params '{"userId":"me","q":"has:attachment"}'  # Get messages with attachments, e.g. to upload to Drive
gws gmail users messages list --params '{"userId":"me","q":"from:news@vendor.com"}'  # find messages from (noisy, important, ...) sender
RAW=$(printf 'From: me\r\nTo: me\r\nSubject: Draft\r\n\r\nBody\r\n' | base64 -w0 | tr '+/' '-_' | tr -d '=')
gws gmail users drafts create --params '{"userId":"me"}' --json "{\"message\":{\"raw\":\"$RAW\"}}" # Create drafts programmatically (safe, no send)

gws workflow +standup-report # combines today’s meetings + open tasks into one object
gws workflow +weekly-digest # weekly meetings + unread count for the week
gws workflow +meeting-prep  # prep for next meeting with agenda, attendees, and relevant docs
gws workflow +email-to-task --message-id MSG_ID --tasklist TASKLIST_ID  # convert an email to a task in a specified tasklist

gws drive files list --params '{"pageSize":20,"orderBy":"modifiedTime desc","fields":"files(id,name,mimeType,modifiedTime)"}' --format table  # List recently modified files in a table
gws drive +upload ./report.pdf --parent FOLDER_ID # Upload file
gws drive files list --params '{"orderBy":"quotaBytesUsed desc","pageSize":20,"fields":"files(id,name,size,mimeType)"}' --format table # Find storage hogs
gws drive about get --params '{"fields":"storageQuota,importFormats,exportFormats,maxUploadSize"}' # audit quota and supported formats

gws docs +write --document DOC_ID --text 'Today: shipped X, blocked by Y, next Z' # Update a status doc with today’s work summary
gws sheets +append --spreadsheet SPREADSHEET_ID --values '2026-03-06,ClientA,Proposal Sent' # Append a new row to a project tracking sheet for lightweight metrics tracking
gws slides presentations create --json '{"title":"Client Weekly Update"}' # Create a new Slides deck for a client update. Then batchUpdate insertText / createSlide requests

gws gmail +watch # stream new mail via Pub/Sub
gws events +subscribe # for Workspace event streams
```

Notes:

- In case `gws drive files ...` returns a HTTP 403 "Caller does not have required permission to use project $PROJECT. Grant the caller the roles/serviceusage.serviceUsageConsumer role, or a custom role with the serviceusage.services.use permission", run:
  `gcloud projects add-iam-policy-binding $PROJECT --member="user:$EMAIL" --role="roles/serviceusage.serviceUsageConsumer"` [Gemini](https://gemini.google.com/app/a2c35e2c687b76b1)
