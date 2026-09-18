"""Evolution API transport (Baileys) — request shapes, auth, resilience."""

import base64
import json

import httpx
import pytest

from core.services import whatsapp_service


@pytest.fixture
def evo_config(client):
    """Point the session-scoped app at a fake Evolution server (restored)."""
    app = client.application
    old = {k: app.config.get(k) for k in ("EVOLUTION_API_URL",
                                          "EVOLUTION_API_KEY",
                                          "EVOLUTION_INSTANCE")}
    app.config.update(EVOLUTION_API_URL="http://evo:8080",
                      EVOLUTION_API_KEY="test-key",
                      EVOLUTION_INSTANCE="basketball-bot")
    try:
        yield app.config
    finally:
        app.config.update(old)


def _mock_session(mocker, status=201, json_data=None, exc=None):
    resp = mocker.MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data if json_data is not None else {}
    if exc is not None:
        resp.raise_for_status.side_effect = exc
    session = mocker.MagicMock()
    session.post.return_value = resp
    session.get.return_value = resp
    session.__enter__.return_value = session
    cls = mocker.patch.object(whatsapp_service.httpx, "Client",
                              return_value=session)
    return cls, session


class TestSendText:
    def test_request_shape(self, client, evo_config, mocker):
        cls, session = _mock_session(mocker)
        assert whatsapp_service.send_text_message("+39 333 123 4567",
                                                 "Ciao") is True
        kwargs = cls.call_args.kwargs
        assert kwargs["base_url"] == "http://evo:8080"
        assert kwargs["headers"] == {"apikey": "test-key"}
        session.post.assert_called_once_with(
            "/message/sendText/basketball-bot",
            json={"number": "393331234567", "text": "Ciao"})

    def test_group_jid_passthrough(self, client, evo_config, mocker):
        _, session = _mock_session(mocker)
        whatsapp_service.send_text_message("120363999@g.us", "Hi staff")
        assert session.post.call_args.kwargs["json"]["number"] == \
            "120363999@g.us"

    def test_masking(self):
        assert whatsapp_service._mask("393331234567") == "393…67"
        assert whatsapp_service._mask("120363999@g.us") == "1203…99@g.us"
        assert whatsapp_service._mask("") == "…"

    def test_logs_mask_recipients(self, client, evo_config, mocker):
        _, session = _mock_session(
            mocker, exc=httpx.HTTPError("boom"))
        mock_logger = mocker.MagicMock()
        mocker.patch.object(whatsapp_service.current_app, "logger",
                            mock_logger)
        whatsapp_service.send_text_message("+393331234567", "x")
        logged = " ".join(
            str(a) for c in mock_logger.method_calls for a in c.args)
        assert "393331234567" not in logged
        assert "393…67" in logged

    def test_empty_destination(self, client, evo_config, mocker):
        _, session = _mock_session(mocker)
        assert whatsapp_service.send_text_message("", "x") is False
        session.post.assert_not_called()

    def test_http_error_is_false(self, client, evo_config, mocker):
        _, session = _mock_session(
            mocker, exc=httpx.HTTPError("boom"))
        assert whatsapp_service.send_text_message("39333123", "x") is False

    def test_unconfigured_skips(self, client, mocker):
        client.application.config.update(EVOLUTION_API_URL="",
                                         EVOLUTION_API_KEY="")
        cls, session = _mock_session(mocker)
        try:
            assert whatsapp_service.send_text_message("39333123",
                                                      "x") is False
        finally:
            client.application.config.update(
                EVOLUTION_API_URL="http://evo:8080",
                EVOLUTION_API_KEY="test-key")
        cls.assert_not_called()


class TestSendDocument:
    def test_payload(self, client, evo_config, mocker):
        _, session = _mock_session(mocker, status=201)
        ok = whatsapp_service.send_document(
            "120363999@g.us", filename="halftime.pdf",
            mimetype="application/pdf", media_base64=b"%PDF-1.4",
            caption="HT")
        assert ok is True
        payload = session.post.call_args.kwargs["json"]
        assert session.post.call_args.args[0] == \
            "/message/sendMedia/basketball-bot"
        assert payload["mediatype"] == "document"
        assert payload["mimetype"] == "application/pdf"
        assert payload["fileName"] == "halftime.pdf"
        assert payload["caption"] == "HT"
        assert base64.b64decode(payload["media"]) == b"%PDF-1.4"

    def test_str_media_passes_through(self, client, evo_config, mocker):
        _, session = _mock_session(mocker)
        whatsapp_service.send_document("39333", filename="a.pdf",
                                       mimetype="application/pdf",
                                       media_base64="QUJD")
        assert session.post.call_args.kwargs["json"]["media"] == "QUJD"


class TestConnectionState:
    def test_open(self, client, evo_config, mocker):
        _, session = _mock_session(
            mocker, json_data={"instance": {"state": "open"}})
        assert whatsapp_service.get_connection_state() == "open"
        assert "/instance/connectionState/basketball-bot" in \
            session.get.call_args.args[0]

    def test_error_is_unknown(self, client, evo_config, mocker):
        _mock_session(mocker, exc=httpx.HTTPError("down"))
        assert whatsapp_service.get_connection_state() == "unknown"

    def test_unconfigured_is_unknown(self, client):
        client.application.config.update(EVOLUTION_API_URL="")
        try:
            assert whatsapp_service.get_connection_state() == "unknown"
        finally:
            client.application.config.update(
                EVOLUTION_API_URL="http://evo:8080")


class TestWrappers:
    def test_otp_uses_transport(self, client, evo_config, mocker):
        send = mocker.patch.object(whatsapp_service, "send_text_message",
                                   return_value=True)
        assert whatsapp_service.send_otp_whatsapp("+39 333", "123456") is True
        args, _ = send.call_args
        assert args[0] == "+39 333"
        assert "123456" in args[1]

    def test_otp_no_phone(self, client, evo_config, mocker):
        send = mocker.patch.object(whatsapp_service, "send_text_message")
        assert whatsapp_service.send_otp_whatsapp("", "123456") is False
        send.assert_not_called()

    def test_game_notification_fans_out(self, client, evo_config, mocker):
        send = mocker.patch.object(whatsapp_service, "send_text_message",
                                   return_value=True)
        game = mocker.MagicMock(opponent="Rivals", date="d", result="W",
                                score_display="1-0", game_type="Season")
        whatsapp_service.send_game_notification(["+391", "", "+392"], game)
        assert send.call_count == 2

    def test_group_notification(self, client, evo_config, mocker):
        send = mocker.patch.object(whatsapp_service, "send_text_message",
                                   return_value=True)
        game = mocker.MagicMock(opponent="R", date="d", result="W",
                                score_display="1-0", game_type="S")
        assert whatsapp_service.send_game_notification_to_group("1@g.us",
                                                                game) is True
        assert send.call_args.args[0] == "1@g.us"


class TestHalftimePdfAttachment:
    def _payload(self, **extra):
        base = {"opponent": "Rivals", "date": "2026-09-18",
                "team_score": 45, "opp_score": 42,
                "player_stats": {"Anna": {"points": 10}}}
        base.update(extra)
        return base

    def _login(self, client, user, team):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
            sess["current_team_id"] = team.id

    def test_pdf_forwarded(self, client, editor_user, default_team, mocker):
        mocker.patch.object(whatsapp_service, "send_text_message",
                            return_value=True)
        doc = mocker.patch.object(whatsapp_service, "send_document",
                                  return_value=True)
        self._login(client, editor_user, default_team)
        resp = client.post(
            "/reports/live/halftime-share",
            data=json.dumps(self._payload(
                phone="+39333", pdf_base64="JVBERg==",
                pdf_filename="ht.pdf")),
            content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data == {"sent": True, "text_sent": True,
                        "text": data["text"],
                        "channel": {"kind": "whatsapp", "phone": "+39333"},
                        "pdf_sent": True}
        assert doc.call_args.kwargs["filename"] == "ht.pdf"
        assert doc.call_args.kwargs["mimetype"] == "application/pdf"

    def test_pdf_failure_keeps_text_sent(self, client, editor_user,
                                         default_team, mocker):
        mocker.patch.object(whatsapp_service, "send_text_message",
                            return_value=True)
        mocker.patch.object(whatsapp_service, "send_document",
                            return_value=False)
        self._login(client, editor_user, default_team)
        resp = client.post(
            "/reports/live/halftime-share",
            data=json.dumps(self._payload(phone="+39333",
                                          pdf_base64="JVBERg==")),
            content_type="application/json")
        # Text was delivered: 200 with separate flags, not a 502 that
        # would invite a duplicate text on retry.
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["text_sent"] is True
        assert data["pdf_sent"] is False
