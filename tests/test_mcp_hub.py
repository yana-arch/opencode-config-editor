import pytest
from conftest import HAS_QT, app

pytestmark = pytest.mark.skipif(not HAS_QT, reason="PySide6 not available")
QDialog, QFileDialog, QMessageBox, QPushButton = app.QDialog, app.QFileDialog, app.QMessageBox, app.QPushButton


@pytest.fixture
def dialog(qapp):
    d = app.MCPTemplateHubDialog(target_mode="opencode")
    yield d
    d.deleteLater()


def _select(d, tid):
    for r in range(d.template_list.count()):
        if d.template_list.item(r).data(app.Qt.UserRole) == tid:
            d.template_list.setCurrentRow(r)
            return
    raise AssertionError(f"template {tid} not in list")


# --- F1 -------------------------------------------------------------------
def test_switching_away_from_remote_does_not_freeze_result(dialog):
    """After the remote template's URL widget is deleted, a later template
    must still produce its own preview/result (no dangling url_edit)."""
    _select(dialog, "remote-sse")
    _select(dialog, "filesystem")
    assert dialog.url_edit is None
    dialog.param_widgets["allowed_directory"].setText("/tmp/sandbox")
    assert dialog.result_server_key == "filesystem"
    assert "/tmp/sandbox" in dialog.result_server_config["command"]
    assert "{allowed_directory}" not in dialog.preview_edit.toPlainText()


# --- F2 -------------------------------------------------------------------
def test_opencode_env_is_emitted_as_environment():
    tmpl = app.get_mcp_template("github")
    cfg = app.instantiate_opencode_mcp(
        tmpl, "github", env_values={"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_x"}
    )
    assert cfg["environment"] == {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_x"}
    assert "env" not in cfg


def test_openclaude_env_stays_env():
    tmpl = app.get_mcp_template("github")
    cfg = app.instantiate_openclaude_mcp(
        tmpl, "github", env_values={"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_x"}
    )
    assert cfg["env"] == {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_x"}
    assert "environment" not in cfg


# --- F7 -------------------------------------------------------------------
def test_install_refused_when_required_arg_blank(dialog, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    _select(dialog, "filesystem")
    dialog.param_widgets["allowed_directory"].setText("   ")
    dialog._on_install()
    assert dialog.result() != QDialog.Accepted
    assert warned


def test_install_refused_when_remote_url_left_untouched(dialog, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    _select(dialog, "remote-sse")
    # The example URL is only a placeholder, so an untouched field is blank.
    assert dialog.result_server_config["url"] == ""
    dialog._on_install()
    assert dialog.result() != QDialog.Accepted
    assert warned


def test_install_succeeds_when_required_input_filled(dialog, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail("unexpected warning"))
    _select(dialog, "filesystem")
    dialog.param_widgets["allowed_directory"].setText("/tmp/sandbox")
    dialog._on_install()
    assert dialog.result() == QDialog.Accepted
    assert dialog.result_server_config["command"][-1] == "/tmp/sandbox"


# --- F8 -------------------------------------------------------------------
def test_env_fields_are_masked_and_preview_redacted(dialog):
    _select(dialog, "github")
    w = dialog.env_widgets["GITHUB_PERSONAL_ACCESS_TOKEN"]
    assert isinstance(w, app.MaskedLineEdit)
    assert w.is_secret is True
    w.set_value("ghp_SECRET123")
    assert "ghp_SECRET123" not in w.edit.text()
    w.set_value("ghp_SECRET123")
    assert "ghp_SECRET123" not in dialog.preview_edit.toPlainText()
    assert dialog.result_server_config["environment"]["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp_SECRET123"


def test_dsn_password_is_redacted_from_preview(dialog):
    _select(dialog, "postgres")
    password = "Hunter2RealPassword"
    dsn = f"postgresql://admin:{password}@db.internal:5432/prod"
    dialog.param_widgets["connection_string"].setText(dsn)
    assert password not in dialog.preview_edit.toPlainText()
    assert dialog.result_server_config["command"][-1] == dsn


# --- F13 ------------------------------------------------------------------
def _click_browse(dialog):
    """Click the Browse button of the selected template's path param."""
    btns = [b for b in dialog.findChildren(QPushButton) if b.property("picker_mode")]
    assert len(btns) == 1
    btns[0].click()


def test_db_path_browse_uses_file_picker(dialog, monkeypatch):
    used = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (used.append("file") or ("/tmp/x.db", ""))))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: (used.append("dir") or "/tmp")))
    _select(dialog, "sqlite")
    _click_browse(dialog)
    assert used == ["file"]
    assert dialog.param_widgets["db_path"].text() == "/tmp/x.db"


def test_directory_param_browse_uses_directory_picker(dialog, monkeypatch):
    used = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (used.append("file") or ("", ""))))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        staticmethod(lambda *a, **k: (used.append("dir") or "/tmp/proj")))
    _select(dialog, "filesystem")
    _click_browse(dialog)
    assert used == ["dir"]
    assert dialog.param_widgets["allowed_directory"].text() == "/tmp/proj"


# --- F14 ------------------------------------------------------------------
def test_zero_matches_clears_selection_and_disables_install(dialog):
    _select(dialog, "filesystem")
    assert dialog.install_btn.isEnabled()
    dialog.search_edit.setText("zzz-no-such-server")
    assert dialog.template_list.count() == 0
    assert dialog.selected_template is None
    assert dialog.result_server_key == ""
    assert dialog.result_server_config == {}
    assert dialog.preview_edit.toPlainText() == ""
    assert not dialog.install_btn.isEnabled()


def test_install_still_refused_after_empty_search(dialog, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    dialog.search_edit.setText("zzz-no-such-server")
    dialog._on_install()
    assert dialog.result_server_key == ""
    assert dialog.result_server_config == {}
    assert not dialog.install_btn.isEnabled()


def test_matching_again_restores_selection_and_install(dialog):
    dialog.search_edit.setText("zzz-no-such-server")
    assert not dialog.install_btn.isEnabled()
    dialog.search_edit.setText("memory")
    assert dialog.template_list.count() == 1
    assert dialog.selected_template.id == "memory"
    assert dialog.result_server_key == "memory"
    assert dialog.install_btn.isEnabled()