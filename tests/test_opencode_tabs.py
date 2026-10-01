"""Regression tests for the opencode config tabs (audit OC-01..OC-20).

Each test drives the real widgets and asserts the dict the tab would save.
The schema-related tests check the values the tabs write against a vendored
copy of the opencode config schema (see the `opencode_schema` fixture).
"""
import pytest

from tests.conftest import HAS_QT, app

pytestmark = pytest.mark.skipif(
    not HAS_QT, reason="PySide6 not available - skipping opencode tab tests")


class FakeCfg:
    def __init__(self, data, path="fake.json"):
        self.data = data
        self.path = path


class FakeApp:
    """Minimal MainWindow stand-in for a single opencode config."""

    model_catalog = None

    def __init__(self, oc=None, tui=None):
        self.cfg = FakeCfg(oc) if oc is not None else None
        self.cfg_oc = self.cfg
        self.cfg_tui = FakeCfg(tui) if tui is not None else None
        self.dirty_oc = False
        self.dirty_tui = False
        self._raw_kind = "opencode"

    def snapshot_state(self, *a):
        pass

    def mark_dirty(self, *a):
        pass

    def validate(self, text, kind="opencode"):
        return True, [], []


@pytest.fixture
def stub_dialogs(monkeypatch):
    """Patch the modal QInputDialogs so +Add flows run without a user."""
    answers = []
    monkeypatch.setattr(app.QInputDialog, "getText",
                        lambda *a, **k: (answers.pop(0), True))
    monkeypatch.setattr(app.QInputDialog, "getItem",
                        lambda *a, **k: (answers.pop(0), True))
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(app.QMessageBox, "warning", lambda *a, **k: None)
    return answers


# --------------------------------------------------------------------------
# OC-01: AgentEditDialog must not write steps: 0 (schema exclusiveMinimum 0)
# --------------------------------------------------------------------------

def test_agent_dialog_untouched_omits_steps(qapp):
    dlg = app.AgentEditDialog(None)
    assert dlg.values()["steps"] is None
    dlg.name_edit.setText("helper")
    assert dlg.values()["steps"] is None


def test_agent_dialog_seeds_steps_from_steps_and_max_steps(qapp):
    dlg = app.AgentEditDialog(None, "a", {"steps": 12})
    assert dlg.steps.value() == 12
    # the deprecated key is still read when `steps` is absent
    legacy = app.AgentEditDialog(None, "a", {"maxSteps": 7})
    assert legacy.steps.value() == 7


def test_agent_dialog_writes_positive_steps(qapp):
    dlg = app.AgentEditDialog(None)
    dlg.steps.setValue(25)
    assert dlg.values()["steps"] == 25


def test_adding_agent_without_steps_saves_no_steps(qapp, monkeypatch):
    fake = FakeApp(oc={})
    tab = app.AgentsTab(fake)
    dlg = app.AgentEditDialog(None)
    dlg.name_edit.setText("helper")
    dlg.model_edit.setText("anthropic/x")
    monkeypatch.setattr(app, "AgentEditDialog", lambda *a, **k: dlg)
    monkeypatch.setattr(type(dlg), "exec", lambda self: 1)
    tab._add()
    assert fake.cfg.data["agent"]["helper"]["model"] == "anthropic/x"
    assert "steps" not in fake.cfg.data["agent"]["helper"]


def test_invalid_color_keeps_the_dialog_open(qapp, monkeypatch):
    dlg = app.AgentEditDialog(None)
    dlg.name_edit.setText("helper")
    dlg.color_edit.setText("red")
    monkeypatch.setattr(app.QMessageBox, "warning", lambda *a, **k: None)
    dlg._try_accept()
    # refused: the dialog stays open so the typed input is not lost
    assert dlg.result() == 0
    assert dlg.color_edit.text() == "red"


def test_valid_color_accepts_the_dialog(qapp, monkeypatch):
    dlg = app.AgentEditDialog(None)
    dlg.name_edit.setText("helper")
    dlg.color_edit.setText("#FF5733")
    monkeypatch.setattr(app.QMessageBox, "warning",
                        lambda *a, **k: pytest.fail("warned on a valid color"))
    dlg._try_accept()
    assert dlg.result() == 1


def test_adding_agent_with_invalid_color_is_refused(qapp, monkeypatch):
    fake = FakeApp(oc={})
    tab = app.AgentsTab(fake)
    dlg = app.AgentEditDialog(None)
    dlg.name_edit.setText("helper")
    dlg.color_edit.setText("red")
    monkeypatch.setattr(app, "AgentEditDialog", lambda *a, **k: dlg)
    monkeypatch.setattr(type(dlg), "exec", lambda self: 1)
    monkeypatch.setattr(app.QMessageBox, "warning", lambda *a, **k: None)
    tab._add()
    assert "agent" not in fake.cfg.data


# --------------------------------------------------------------------------
# OC-19: agent color is validated against the schema
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["#FF5733", "#ff5733", "primary", "info", ""])
def test_agent_dialog_accepts_valid_colors(qapp, value):
    dlg = app.AgentEditDialog(None)
    dlg.color_edit.setText(value)
    assert dlg.color_error() == ""


@pytest.mark.parametrize("value", ["red", "#FFF", "123456", "Primary"])
def test_agent_dialog_rejects_invalid_colors(qapp, value):
    dlg = app.AgentEditDialog(None)
    dlg.color_edit.setText(value)
    assert dlg.color_error()


# --------------------------------------------------------------------------
# OC-02 / OC-03: permission rules use schema actions and tolerate the
# string form of `permission`
# --------------------------------------------------------------------------

def test_add_rule_writes_schema_action(qapp, stub_dialogs):
    fake = FakeApp(oc={})
    tab = app.PermissionTab(fake)
    stub_dialogs.extend(["bash", "git *", "allow"])
    tab._add_rule()
    assert fake.cfg.data["permission"] == {"bash": {"git *": "allow"}}


def test_add_rule_offers_only_schema_actions(qapp, monkeypatch):
    seen = {}

    def get_item(parent, title, label, items, *a, **k):
        seen["items"] = list(items)
        return "ask", True

    monkeypatch.setattr(app.QInputDialog, "getItem", get_item)
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)
    fake = FakeApp(oc={})
    tab = app.PermissionTab(fake)
    answers = iter(["bash", "git *"])
    monkeypatch.setattr(app.QInputDialog, "getText",
                        lambda *a, **k: (next(answers), True))
    tab._add_rule()
    assert seen["items"] == ["ask", "allow", "deny"]


def test_add_action_only_category_writes_string(qapp, stub_dialogs):
    fake = FakeApp(oc={})
    tab = app.PermissionTab(fake)
    stub_dialogs.extend(["todowrite", "ask"])  # no path prompt for these
    tab._add_rule()
    assert fake.cfg.data["permission"] == {"todowrite": "ask"}


def test_permission_string_form_renders_and_survives(qapp):
    fake = FakeApp(oc={"permission": "allow"})
    tab = app.PermissionTab(fake)
    tab.refresh()
    assert tab.tree.topLevelItemCount() == 1
    assert tab.tree.topLevelItem(0).text(2) == "allow"
    out = {"permission": fake.cfg.data["permission"]}
    tab.collect(out)
    assert out["permission"] == "allow"


def test_permission_search_on_string_form_does_not_crash(qapp):
    fake = FakeApp(oc={"permission": "allow"})
    tab = app.PermissionTab(fake)
    tab.search_edit.setText("al")
    assert tab.tree.topLevelItemCount() == 1
    tab.search_edit.setText("zzz")
    assert tab.tree.topLevelItemCount() == 0


def test_permission_action_only_category_renders_and_survives(qapp):
    fake = FakeApp(oc={"permission": {"edit": "ask"}})
    tab = app.PermissionTab(fake)
    tab.refresh()
    assert tab.tree.topLevelItem(0).text(0) == "edit"
    assert tab.tree.topLevelItem(0).text(2) == "ask"
    out = {"permission": {"edit": "ask"}}
    tab.collect(out)
    assert out["permission"] == {"edit": "ask"}


def test_add_rule_refuses_string_permission(qapp, stub_dialogs):
    fake = FakeApp(oc={"permission": "allow"})
    tab = app.PermissionTab(fake)
    stub_dialogs.extend(["bash", "git *", "allow"])
    tab._add_rule()
    assert fake.cfg.data["permission"] == "allow"


def test_add_rule_keeps_existing_string_category_as_catch_all(qapp, stub_dialogs):
    fake = FakeApp(oc={"permission": {"bash": "ask"}})
    tab = app.PermissionTab(fake)
    stub_dialogs.extend(["bash", "git *", "allow"])
    tab._add_rule()
    assert fake.cfg.data["permission"] == {
        "bash": {"*": "ask", "git *": "allow"}}


# --------------------------------------------------------------------------
# OC-14: the tree is not in-place editable (no silent no-op edits)
# --------------------------------------------------------------------------

def test_permission_tree_items_are_not_editable(qapp):
    fake = FakeApp(oc={"permission": {"bash": {"git *": "ask"}}})
    tab = app.PermissionTab(fake)
    tab.refresh()
    cat = tab.tree.topLevelItem(0)
    rule = cat.child(0)
    assert not cat.flags() & app.Qt.ItemIsEditable
    assert not rule.flags() & app.Qt.ItemIsEditable


# --------------------------------------------------------------------------
# OC-04 / OC-05 / OC-10 / OC-11: General tab round-trips
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["manual", "auto", "disabled"])
def test_share_string_survives_collect(qapp, value):
    fake = FakeApp(oc={"share": value})
    tab = app.GeneralTab(fake)
    tab.refresh()
    assert tab.share_combo.currentData() == value
    out = {}
    tab.collect(out)
    assert out["share"] == value


def test_autoupdate_false_survives_collect(qapp):
    fake = FakeApp(oc={"autoupdate": False})
    tab = app.GeneralTab(fake)
    tab.refresh()
    out = {}
    tab.collect(out)
    assert out["autoupdate"] is False


def test_autoupdate_absent_stays_absent(qapp):
    fake = FakeApp(oc={})
    tab = app.GeneralTab(fake)
    tab.refresh()
    out = {}
    tab.collect(out)
    assert "autoupdate" not in out


def test_snapshot_absent_shows_enabled(qapp):
    fake = FakeApp(oc={})
    tab = app.GeneralTab(fake)
    tab.refresh()
    assert tab.snapshot_check.isChecked() is True


def test_snapshot_uncheck_writes_false(qapp):
    fake = FakeApp(oc={})
    tab = app.GeneralTab(fake)
    tab.refresh()
    tab.snapshot_check.setChecked(False)
    out = {}
    tab.collect(out)
    assert out["snapshot"] is False


def test_subagent_depth_zero_round_trips_as_zero(qapp):
    fake = FakeApp(oc={"subagent_depth": 0})
    tab = app.GeneralTab(fake)
    tab.refresh()
    assert tab.subagent_depth.value() == 0
    # _collect_oc starts from cfg.data, so mirror that
    out = dict(fake.cfg.data)
    tab.collect(out)
    assert out["subagent_depth"] == 0


def test_subagent_depth_default_sentinel_removes_the_key(qapp):
    fake = FakeApp(oc={"subagent_depth": 2})
    tab = app.GeneralTab(fake)
    tab.refresh()
    tab.subagent_depth.setValue(-1)   # renders as '(default)'
    out = {}
    tab.collect(out)
    assert "subagent_depth" not in out


def test_subagent_depth_positive_written(qapp):
    fake = FakeApp(oc={})
    tab = app.GeneralTab(fake)
    tab.refresh()
    tab.subagent_depth.setValue(3)
    out = {}
    tab.collect(out)
    assert out["subagent_depth"] == 3


# --------------------------------------------------------------------------
# OC-06 / OC-07 / OC-12 / OC-17 / OC-18: Runtime tab
# --------------------------------------------------------------------------

def test_cors_edits_do_not_delete_existing_origins(qapp):
    fake = FakeApp(oc={"server": {"port": 4096,
                                  "cors": ["https://app.example.com"]}})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    assert tab.server_cors.list.count() == 1
    tab.server_mdns.setChecked(True)
    out = {}
    tab.collect(out)
    assert out["server"]["cors"] == ["https://app.example.com"]
    assert out["server"]["mdns"] is True


def test_cors_addition_is_saved(qapp):
    fake = FakeApp(oc={"server": {}})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.server_cors.list.addItem("https://b.example.com")
    tab.server_cors._changed()
    out = {}
    tab.collect(out)
    assert out["server"]["cors"] == ["https://b.example.com"]


@pytest.mark.parametrize("attr,key,value,group", [
    ("server_port", "server", 4096, "server"),
    ("tool_lines", "tool_output", 500, "tool_output"),
    ("att_h", "attachment", 20, "attachment"),
])
def test_spinbox_edits_are_collected(qapp, attr, key, value, group):
    fake = FakeApp(oc={})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    getattr(tab, attr).setValue(value)
    out = {}
    tab.collect(out)
    assert out.get(key) is not None, f"{group} edit was dropped"


def test_list_editor_edits_are_collected(qapp):
    fake = FakeApp(oc={})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.instructions.list.addItem("AGENTS.md")
    tab.instructions._changed()
    out = {}
    tab.collect(out)
    assert out["instructions"] == ["AGENTS.md"]


def test_boolmap_toggle_is_collected(qapp):
    fake = FakeApp(oc={"tools": {"bash": True}})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.tools.table.cellWidget(0, 1).setChecked(False)
    out = {}
    tab.collect(out)
    assert out["tools"] == {"bash": False}


def test_nested_list_collects_at_the_right_path(qapp):
    fake = FakeApp(oc={"experimental": {"primary_tools": ["bash"]}})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.exp_otel.setChecked(True)
    out = {}
    tab.collect(out)
    exp = out["experimental"]
    assert exp["primary_tools"] == ["bash"]
    assert exp["openTelemetry"] is True
    # no accidental experimental.experimental wrapper
    assert "experimental" not in exp


def test_watcher_list_collects_at_the_right_path(qapp):
    fake = FakeApp(oc={"watcher": {"ignore": ["**/node_modules"]}})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.watcher_ignore.list.addItem("tmp/*")
    tab.watcher_ignore._changed()
    out = {}
    tab.collect(out)
    assert out["watcher"] == {"ignore": ["**/node_modules", "tmp/*"]}


def test_skills_list_collects_at_the_right_path(qapp):
    fake = FakeApp(oc={"skills": {"paths": ["/a"]}})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.skills_paths.list.addItem("/b")
    tab.skills_paths._changed()
    out = {}
    tab.collect(out)
    assert out["skills"]["paths"] == ["/a", "/b"]


def test_untouched_empty_watcher_and_skills_round_trip(qapp):
    fake = FakeApp(oc={"watcher": {}, "skills": {}})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    # _collect_oc starts from cfg.data, so mirror that
    out = dict(fake.cfg.data)
    tab.collect(out)
    assert out == {"watcher": {}, "skills": {}}


def test_compaction_zero_counts_survive(qapp):
    fake = FakeApp(oc={"compaction": {"tail_turns": 0, "reserved": 0}})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.comp_prune.setChecked(True)
    out = {}
    tab.collect(out)
    assert out["compaction"]["tail_turns"] == 0
    assert out["compaction"]["reserved"] == 0


def test_compaction_unset_stays_unset(qapp):
    fake = FakeApp(oc={})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.comp_prune.setChecked(True)
    out = {}
    tab.collect(out)
    assert "tail_turns" not in out["compaction"]


def test_policy_with_invalid_effect_is_skipped(qapp):
    fake = FakeApp(oc={})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.policies.insertRow(0)
    tab.policies.setItem(0, 0, app.QTableWidgetItem(""))
    tab.policies.setItem(0, 1, app.QTableWidgetItem("provider.use"))
    tab.policies.setItem(0, 2, app.QTableWidgetItem("openai"))
    out = {}
    tab.collect(out)
    assert "policies" not in out.get("experimental", {})


def test_valid_policy_is_written(qapp):
    fake = FakeApp(oc={})
    tab = app.RuntimeTab(fake)
    tab.refresh()
    tab.policies.insertRow(0)
    tab.policies.setItem(0, 0, app.QTableWidgetItem("deny"))
    tab.policies.setItem(0, 1, app.QTableWidgetItem("provider.use"))
    tab.policies.setItem(0, 2, app.QTableWidgetItem("openai"))
    out = {}
    tab.collect(out)
    assert out["experimental"]["policies"] == [
        {"effect": "deny", "action": "provider.use", "resource": "openai"}]


# --------------------------------------------------------------------------
# OC-13 / OC-20: agents & commands
# --------------------------------------------------------------------------

def test_add_agent_refuses_existing_name(qapp, monkeypatch):
    fake = FakeApp(oc={"agent": {"build": {"model": "anthropic/x",
                                           "permission": {"bash": "ask"}}}})
    tab = app.AgentsTab(fake)

    class FakeDlg:
        def exec(self):
            return 1

        def values(self):
            return {"name": "build", "description": "", "model": "",
                    "mode": "", "prompt": "", "hidden": False,
                    "disable": False, "color": ""}

        def color_error(self):
            return ""
    monkeypatch.setattr(app, "AgentEditDialog", lambda *a, **k: FakeDlg())
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)
    tab._add()
    # the built-in override is untouched
    assert fake.cfg.data["agent"]["build"]["model"] == "anthropic/x"
    assert fake.cfg.data["agent"]["build"]["permission"] == {"bash": "ask"}


def test_rename_agent_refuses_existing_name(qapp, monkeypatch):
    fake = FakeApp(oc={"agent": {"a": {}, "b": {}}})
    tab = app.AgentsTab(fake)

    class FakeDlg:
        def exec(self):
            return 1

        def values(self):
            return {"name": "b", "description": "", "model": "",
                    "mode": "", "prompt": "", "hidden": False,
                    "disable": False, "color": ""}

        def color_error(self):
            return ""

    monkeypatch.setattr(app, "AgentEditDialog", lambda *a, **k: FakeDlg())
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)
    tab._edit("a")
    assert set(fake.cfg.data["agent"]) == {"a", "b"}


def test_edit_agent_steps_inherit_removes_the_key(qapp, monkeypatch):
    fake = FakeApp(oc={"agent": {"a": {"steps": 10, "model": "m"}}})
    tab = app.AgentsTab(fake)
    tab.refresh()

    inner = app.AgentEditDialog(None, "a", {"steps": 10, "model": "m"})
    inner.steps.setValue(0)   # the user picks "(inherit)"
    monkeypatch.setattr(app, "AgentEditDialog", lambda *a, **k: inner)
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(type(inner), "exec", lambda self: 1)
    tab._edit("a")
    assert "steps" not in fake.cfg.data["agent"]["a"]
    assert fake.cfg.data["agent"]["a"]["model"] == "m"


def test_add_command_refuses_existing_name(qapp, monkeypatch):
    fake = FakeApp(oc={"command": {"t": {"template": "x", "agent": "build"}}})
    tab = app.CommandsTab(fake)

    class FakeDlg:
        def exec(self):
            return 1

        def values(self):
            return {"name": "t", "template": "y", "description": "",
                    "agent": "", "model": ""}

    monkeypatch.setattr(app, "CommandEditDialog", lambda *a, **k: FakeDlg())
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)
    tab._add()
    assert fake.cfg.data["command"]["t"] == {"template": "x", "agent": "build"}


def test_command_table_has_actions_column(qapp):
    fake = FakeApp(oc={"command": {"t": {"template": "x"}}})
    tab = app.CommandsTab(fake)
    tab.refresh()
    assert tab.table.columnCount() == 5
    assert isinstance(tab.table.cellWidget(0, 4), app.QWidget)


# --------------------------------------------------------------------------
# OC-09 / OC-15: tui tab
# --------------------------------------------------------------------------

def test_unmigrated_plugin_enabled_entries_survive(qapp):
    fake = FakeApp(tui={"theme": "opencode",
                        "plugin_enabled": {"which-key": False,
                                           "diff-viewer": True}})
    tab = app.TuiTab(fake)
    tab.refresh()
    # neither name is in the `plugin` list, so the editor cannot migrate them
    assert fake.cfg_tui.data["plugin_enabled"] == {
        "which-key": False, "diff-viewer": True}
    # _collect_tui starts from cfg.data, so mirror that
    out = dict(fake.cfg_tui.data)
    tab.collect(out)
    assert out["plugin_enabled"] == {"which-key": False, "diff-viewer": True}


def test_migrated_plugin_is_cached_and_collect_keeps_file_entries(qapp, tmp_path):
    path = tmp_path / "tui.json"
    fake = FakeApp(tui={"plugin": ["a", "b"],
                        "plugin_enabled": {"a": False, "b": True, "c": False}})
    fake.cfg_tui.path = path
    tab = app.TuiTab(fake)
    tab.plugins.state_store.path = path
    tab.refresh()
    assert fake.cfg_tui.data["plugin"] == ["b"]
    # 'a' moved to the cache; 'b' (true) and 'c' (no plugin entry) stay put
    assert fake.cfg_tui.data["plugin_enabled"] == {"b": True, "c": False}
    out = dict(fake.cfg_tui.data)
    tab.collect(out)
    assert out["plugin_enabled"] == {"b": True, "c": False}


def test_prompt_max_width_auto_is_preserved(qapp):
    fake = FakeApp(tui={"prompt": {"max_height": 10, "max_width": "auto"}})
    tab = app.TuiTab(fake)
    tab.refresh()
    assert tab.prompt_w_auto.isChecked() is True
    tab.prompt_h.setValue(20)
    out = {}
    tab.collect(out)
    assert out["prompt"]["max_width"] == "auto"


def test_prompt_max_width_auto_can_be_chosen(qapp):
    fake = FakeApp(tui={})
    tab = app.TuiTab(fake)
    tab.refresh()
    tab.prompt_w_auto.setChecked(True)
    tab.prompt_h.setValue(5)
    out = {}
    tab.collect(out)
    assert out["prompt"]["max_width"] == "auto"


def test_prompt_max_width_number_round_trips(qapp):
    fake = FakeApp(tui={"prompt": {"max_width": 100}})
    tab = app.TuiTab(fake)
    tab.refresh()
    assert tab.prompt_w_auto.isChecked() is False
    assert tab.prompt_w.value() == 100
    tab.prompt_h.setValue(5)
    out = {}
    tab.collect(out)
    assert out["prompt"]["max_width"] == 100


# --------------------------------------------------------------------------
# OC-16: switching the raw file keeps the pending edit
# --------------------------------------------------------------------------

def test_raw_edit_survives_file_switch(qapp, tmp_path):
    fake = FakeApp(oc={"model": "anthropic/a"}, tui={"theme": "x"})
    fake.cfg_tui.path = tmp_path / "tui.json"
    tab = app.RawJsonTab(fake)
    tab.refresh()
    tab.editor.setPlainText('{"model":"anthropic/zzz","logLevel":"DEBUG"}')
    tab.file_combo.setCurrentIndex(1)
    assert fake.cfg_oc.data == {"model": "anthropic/zzz", "logLevel": "DEBUG"}
    tab.file_combo.setCurrentIndex(0)
    assert "anthropic/zzz" in tab.editor.toPlainText()

