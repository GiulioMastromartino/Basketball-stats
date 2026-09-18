# Training Planner

Plan practices as timed agenda blocks, link drills to your playbook, track attendance, and print a session storyboard PDF.

Click **Training** in the sidebar (`/trainings/`, upcoming first). All training routes require login + team context.

---

## Creating a Session

Post title + date to create, then open the detail page to build it out:

```
POST /trainings/new          title, session_date (YYYY-MM-DD, required)
                             start_time (HH:MM), location, focus, notes (optional)
```

The session stores a `post_notes` debrief field — write it up after practice:

```
POST /trainings/<id>/edit    title, session_date, start_time, location,
                             focus, notes, post_notes
POST /trainings/<id>/delete
```

---

## Agenda Segments

A session is a list of timed blocks. Each segment can link to a play from your playbook (the drill to run), so the storyboard reads like a practice script.

```
POST /trainings/<id>/segments/add        title, duration_min, play_id, notes
POST /trainings/segments/<seg_id>/move   direction (reorder)
POST /trainings/segments/<seg_id>/edit
POST /trainings/segments/<seg_id>/delete
```

The detail page totals segment minutes so you can see whether the plan fits the slot.

---

## Reusable Segment Templates

Save any agenda block as a team-wide template (with an optional category), then apply it into future sessions. Templates track `usage_count`, so your most-used drills surface first.

```
POST /trainings/<id>/templates/create                  from a segment
POST /trainings/<id>/templates/<template_id>/apply     into a session
POST /trainings/templates/<template_id>/delete
```

---

## Attendance

Seed one row per roster player, then mark statuses:

```
POST /trainings/<id>/attendance/seed
POST /trainings/attendance/<attendance_id>/status    status
```

Statuses are the app's attendance set (present/absent variants — see `ATTENDANCE_STATUSES` in `web/routes/training.py`).

---

## Export & Import

- **Storyboard PDF**: `GET /trainings/<id>/pdf` — printable session plan with segments, linked plays, and timing.
- **File export**: `GET /trainings/<id>/export` — session as a JSON file (backup or copy between teams).
- **File import**: `POST /trainings/import` — restore a previously exported file (validated; bad files are rejected with an error, never half-imported).

---

## Related

- [Plays Management](plays.md) — drills link to playbook entries
- [Coaching Toolkit](coaching.md) — drill suggestions feed what to train
- [PDF Exports](pdf-exports.md) — the rest of the report catalog
