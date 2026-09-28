"""Google Drive linking: connect, callback, disconnect, and per-type toggles.

Registered at ``/integrations``. Every route is a no-op 404 when Drive sync is
not configured, so the feature disappears cleanly instead of surfacing 500s on
a server that has no OAuth client set up.

Security notes:
* ``state`` is a signed, expiring token whose payload must match the
  currently authenticated user. Both checks are required — verifying only the
  signature would let a valid token minted for another account be replayed.
* Disconnect is POST + CSRF protected. It deletes our stored token but
  deliberately leaves already-synced files in the user's Drive.
"""

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    request,
    url_for,
)
from flask_login import current_user, login_required

from core.services import drive_service, drive_sync_types

integrations_bp = Blueprint("integrations", __name__)

SETTINGS_SECTION = "settings"


def _require_drive_enabled() -> None:
    """404 rather than 500 when the feature is unconfigured.

    Hiding the surface beats showing a connect button that cannot work.
    """
    if not drive_service.is_enabled():
        abort(404)


@integrations_bp.route("/google/start")
@login_required
def google_start():
    _require_drive_enabled()
    state = drive_service.build_state(current_user.id)
    return redirect(drive_service.build_auth_url(state))


@integrations_bp.route("/google/callback")
@login_required
def google_callback():
    _require_drive_enabled()

    if request.args.get("error"):
        # User declined, or the consent screen refused the request.
        flash(
            "Google Drive was not connected: "
            f"{request.args.get('error')}.", "warning",
        )
        return redirect(url_for("main.admin_panel", section=SETTINGS_SECTION))

    code = request.args.get("code")
    if not code:
        flash("Google did not return an authorization code.", "warning")
        return redirect(url_for("main.admin_panel", section=SETTINGS_SECTION))

    # Both checks matter: signature proves we minted it, uid proves it was
    # minted for *this* user.
    state_uid = drive_service.verify_state(request.args.get("state"))
    if state_uid is None or state_uid != int(current_user.id):
        current_app.logger.warning(
            "Rejected Google Drive callback with invalid state for user %s",
            current_user.id,
        )
        flash("Google Drive link failed verification. Please try again.", "danger")
        return redirect(url_for("main.admin_panel", section=SETTINGS_SECTION))

    try:
        drive_service.connect(int(current_user.id), code)
    except drive_service.DriveSyncError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.admin_panel", section=SETTINGS_SECTION))

    flash("Google Drive connected.", "success")
    return redirect(url_for("main.admin_panel", section=SETTINGS_SECTION))


@integrations_bp.route("/google/disconnect", methods=["POST"])
@login_required
def google_disconnect():
    _require_drive_enabled()
    drive_service.disconnect(int(current_user.id))
    flash(
        "Google Drive disconnected. Files already in your Drive were kept.",
        "success",
    )
    return redirect(url_for("main.admin_panel", section=SETTINGS_SECTION))


@integrations_bp.route("/google/prefs", methods=["POST"])
@login_required
def google_update_prefs():
    """Persist the master switch and the per-document-type toggles."""
    _require_drive_enabled()
    user_id = int(current_user.id)

    if not drive_service.is_connected(user_id):
        flash("Connect Google Drive before choosing what to sync.", "warning")
        return redirect(url_for("main.admin_panel", section=SETTINGS_SECTION))

    # Unavailable types are ignored by save_prefs even if a hand-crafted POST
    # includes them, so this only needs to forward what was submitted.
    submitted = {
        spec["key"]: bool(request.form.get(f"doc_type_{spec['key']}"))
        for spec in drive_sync_types.list_types(include_unavailable=True)
    }
    try:
        drive_service.save_prefs(
            user_id, bool(request.form.get("auto_upload")), submitted
        )
    except drive_service.DriveSyncError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("main.admin_panel", section=SETTINGS_SECTION))

    flash("Google Drive sync preferences saved.", "success")
    return redirect(url_for("main.admin_panel", section=SETTINGS_SECTION))
