"""Registry of document types that can be synced to a user's Google Drive.

Adding a new synced artefact type is a single entry here plus one call to
``drive_service.enqueue_or_upload()`` at the point the artefact is generated.
Nothing else — no new table, no new route, no schema change.

Folder taxonomy in the user's Drive::

    <root>/<Team name>/<folder>/<file>.pdf

``root`` comes from ``GOOGLE_DRIVE_ROOT_FOLDER``. Teams nest beneath it and the
leaf level is the ``folder`` value below, so each team keeps its own branch and
a user on three teams gets three branches automatically.

``available=False`` entries are declared but not yet wired up; the settings UI
renders them greyed out as "coming soon" so the taxonomy is visible before the
feature lands, and they are rejected by the service if requested.
"""

# Key is the stable doc_type string persisted in google_drive_doc_prefs and
# used as the folder_cache key. Never rename a key once users have saved
# preferences against it — add a new entry instead.
DOC_SYNC_TYPES = {
    "trainings": {
        "folder": "Trainings",
        "label": "Training session PDFs",
        "description": "Every training session PDF you export is copied to your Drive.",
        "available": True,
    },
    "games": {
        "folder": "Games",
        "label": "Game box scores",
        "description": "Game summaries you export are copied to your Drive.",
        "available": False,
    },
    "reports": {
        "folder": "Reports",
        "label": "Season reports",
        "description": "Season and team reports you export are copied to your Drive.",
        "available": False,
    },
    "playbooks": {
        "folder": "Playbooks",
        "label": "Play diagrams",
        "description": "Play diagrams you export are copied to your Drive.",
        "available": False,
    },
}


def is_valid_doc_type(doc_type: str) -> bool:
    return doc_type in DOC_SYNC_TYPES


def is_available(doc_type: str) -> bool:
    """True when the type is registered *and* actually wired up."""
    spec = DOC_SYNC_TYPES.get(doc_type)
    return bool(spec and spec.get("available"))


def get_spec(doc_type: str):
    return DOC_SYNC_TYPES.get(doc_type)


def folder_for(doc_type: str):
    spec = DOC_SYNC_TYPES.get(doc_type)
    return spec["folder"] if spec else None


def list_types(include_unavailable: bool = False):
    """Registry entries as an ordered list, for rendering the settings UI."""
    items = []
    for key, spec in DOC_SYNC_TYPES.items():
        if not include_unavailable and not spec.get("available"):
            continue
        items.append({
            "key": key,
            "folder": spec["folder"],
            "label": spec["label"],
            "description": spec.get("description", ""),
            "available": bool(spec.get("available")),
        })
    return items
