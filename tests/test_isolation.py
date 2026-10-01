import os
from pathlib import Path

import pytest

import conftest


def test_both_conftest_import_paths_share_the_isolated_app():
    """Test modules import `conftest` and `tests.conftest`. Both must yield the
    one app the autouse fixtures patch, or tests write into the developer's
    real ~/.config/opencode-config-editor."""
    pwd = pytest.importorskip("pwd")
    import tests.conftest as tests_conftest
    app = tests_conftest.app
    assert app is conftest.app
    real_appdir = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".config" / app.APP_NAME
    for path in (app.USER_CONFIG_DIR, app.PROVIDER_TRASH_FILE, app.PLUGIN_STATE_CACHE):
        assert path != real_appdir and real_appdir not in path.parents
