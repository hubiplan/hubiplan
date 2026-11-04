---
key: page.aufgaben
titel: Tasks
bereich: start
rechte: [todos.view]
routen: [/aufgaben]
stichworte: [Todo, Tasks]
---

Create personal tasks with a title and an optional description and due date. Personal tasks are private. After creation, edits are saved automatically. Completed tasks appear under Done. Deleted tasks can be restored from the trash for 30 days. Export personal tasks downloads your private tasks.

Shared tasks are also visible to selected people or current role holders. View permission allows reading; edit permission also allows changes and completion. Only the responsible account can delete or transfer responsibility. Under My account › Notifications, disable email and push notices when tasks are shared. Authorised role managers can take over orphaned shared tasks when the responsible account permanently loses access; personal tasks remain hidden. The outbox stores only a neutral delivery record for task notices.

Configure email and push under My account › Notifications. For each task with a due date, choose reminder times and channels or disable notices. Responsible participants are reminded; without an assignment, all participants with edit permission are reminded. Date-only deadlines last until the end of the day and reminders arrive at 8 am; timed deadlines use their exact time. Overdue tasks receive exactly one additional notice at 8 am the next day. Highlighting in HUBIplan remains active independently of email and push. Optionally move completed one-off tasks to the trash after twelve months; this is off by default. Recurring task history is excluded. In your profile, personal tasks can still be exported or permanently deleted after a role ends.

Under Attachments, upload multiple files by selecting them or dropping them in the upload area. Each file may be up to 20 MB; the document repository’s file types and safety checks apply. Restore removed attachments from the attachment trash for 30 days. Document links grant no additional repository permissions: without access, only a placeholder appears. The personal export downloads a ZIP file with tasks, settings and authorised files, including your private tasks after a role ends.

Under Repeat, choose daily, weekly, monthly or yearly occurrences with an interval and an optional end date or total count. Completing a task creates exactly one next occurrence. Month-end dates and 29 February retain their original anchor; late completion skips past due dates. Choose whether the interval starts from the previous due date or from completion. Content changes can apply only to this occurrence or to all following ones. Document links and personal reminder rules are inherited; uploaded files are not. Reopening or undoing an occurrence may retract its successor only while it is untouched. End series keeps an existing open occurrence; the series trash deletes and restores the entire history without creating an extra occurrence.

For recurring tasks, Transfer responsibility applies to the entire shared history and future continuation. If earlier private occurrences remain, the transfer is rejected to protect their contents; review their sharing permissions explicitly first.

Use Target unit to share with allowed neighbouring levels on the same instance. Add same-named roles explicitly for the displayed units; units added later are not included automatically. A shared task is completed once for everyone. With a separate occurrence for each unit, each target unit owns its own copy and, for recurring tasks, an independent sequence. The distribution mode is fixed after sharing. Local editors manage notes, attachments and participants within their unit. Titles, descriptions and due dates remain controlled centrally. The source receives only progress, including the local occurrence number, due date, completion time and account. Central updates affect open copies while preserving local additions and completed history. Removing a target unit or deleting the source stops future occurrences and access to source attachments; the target unit retains its local data. When it revokes a local share, current permissions also apply to files, undo and reminders. For shared tasks, undo uses the authorised target context.

## Tasks linked to events

Link a task to an event in your own calendar. The event offers links to its tasks and to creating a linked task. The task owner can change or remove the link under “Linked event”. Calendar and task permissions remain independent: linking does not share either object. Without calendar permission, only “Event unavailable” appears. Deleting the event keeps the task and removes its link. Due dates do not move automatically with the event. A recurring event is linked as a whole series, rather than an individual occurrence.

## Member tasks

The responsible account can explicitly select current members under “Share in the member portal” (view only or allowed to complete) or publish an open offer. Current unit members can view an offer; department offers are limited to their members. Exactly one person can claim it, complete it or release an open claim. Every read, change and file download checks current membership, portal access and task publication. Members receive no administration rights and cannot change titles, due dates or participants. Document references grant no additional repository access.

Publication initially applies only to the selected occurrence. Explicitly enabling “Also share following occurrences in the member portal” copies it into future occurrences; offers become available to claim again. Completing and reopening preserve the existing protections for subsequent occurrences. Assigned members allowed to complete, or the member who claimed an offer, receive reminders according to their notification preferences.

Use “My area › Tasks” to view open and completed tasks. Mail and push links select the matching portal access. Revoked access, ended membership or a disabled portal prevents further access.

## Creating tasks

“New task” opens a dialog. Enter the title, description, due date and sharing before creating the task. After “Create”, the same dialog stays open for attachments, reminders, recurrence and member access; “Done” closes it. Existing tasks save as usual and unsaved access settings are checked before closing. The description uses a wide, resizable text field. Status and filters share one row on larger screens and wrap on smaller screens.

## Tasks across separate installations

In the task dialog, **Share with another installation** selects a confirmed connection. Enable the task packet in the connection and have the receiving side accept it first. Each task also needs its own explicit grant. New offers appear under **Tasks from other installations** and must be adopted by a responsible local account.

- **Separate copy with independent completion:** Each receiving unit completes independently. The source only sees occurrence, deadline and progress; local notes, additional attachments and account names are not returned. Open copies receive central content changes. Completed copies retain their content. Revocation stops further updates and future occurrences; adopted content stays local. Source attachments still require a current grant.
- **One jointly completed task:** Reading and completion are checked at the source. Completion applies across installations; reload after a version conflict. An unreachable source cannot confirm a new completion state. Revocation, a paused connection or an unconfirmed key change removes access.

After adoption, local task permissions apply. Another board member does not automatically gain access. The source controls whether the receiving side may complete a task. The distribution mode cannot be changed after the first grant. Future occurrences require **Also share future occurrences**. Separate copies then have independent local sequences; jointly completed tasks create successors at the source.
