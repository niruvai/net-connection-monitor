import pytest

from tests.conftest import ScriptedChecker, wait_until
from core.models import ConnectionState as S
from main import build_main_window


@pytest.fixture
def window(make_controller, qapp):
    checker = ScriptedChecker(True)
    c = make_controller(checker)
    c.monitor.set_interval(0.03)
    w, tray = build_main_window(c, with_tray=False)
    w.show()
    c.start()
    yield w, c, checker
    w.hide()


def headline(w):
    return w.dashboard.headline.text()


def test_dashboard_follows_connection_state(window, qapp):
    w, c, checker = window
    assert wait_until(lambda: headline(w) == "ONLINE", app=qapp)
    assert w.dashboard.indicator.state == "online"

    checker.reachable = False
    assert wait_until(lambda: headline(w) == "INTERNET DISCONNECTED", app=qapp)
    assert w.dashboard.indicator.state == "offline"
    assert "Down for" in w.dashboard.subline.text()
    assert w.dashboard.cards["disconnects"]._value.text() == "1"
    assert w.dashboard.cards["ping"]._value.text() == "—"

    checker.reachable = True
    assert wait_until(lambda: "INTERNET IS BACK" in headline(w), app=qapp)
    assert "😂" in headline(w)
    assert w.dashboard.indicator.state == "online"
    assert w.dashboard.cards["outage"]._value.text() == "—"
    assert w.history_page.table.rowCount() == 1


def test_pause_button_and_paused_display(window, qapp):
    w, c, _ = window
    assert wait_until(lambda: c.state is S.ONLINE, app=qapp)
    w.dashboard.pause_button.click()
    assert c.paused and headline(w) == "MONITORING PAUSED"
    assert w.dashboard.pause_button.text() == "Resume monitoring"
    w.dashboard.pause_button.click()
    assert not c.paused and headline(w) == "ONLINE"


def test_history_clear_and_empty_state(window, qapp):
    w, c, checker = window
    assert wait_until(lambda: c.state is S.ONLINE, app=qapp)
    assert not w.history_page.clear_button.isEnabled()
    checker.reachable = False
    assert wait_until(lambda: c.state is S.OFFLINE, app=qapp)
    checker.reachable = True
    assert wait_until(lambda: w.history_page.clear_button.isEnabled(), app=qapp)
    c.clear_history()
    assert w.history_page.table.rowCount() == 0
    assert w.history_page.summary.text() == "Nothing recorded"


def test_settings_page_edits_controller(window, qapp):
    w, c, _ = window
    page = w.settings_page
    page.volume.setValue(25)
    page.sounds.setChecked(False)
    page.dark.setChecked(False)
    page.interval.setValue(5.0)
    assert (c.settings.volume, c.settings.sounds_enabled, c.settings.dark_mode, c.settings.check_interval) == (25, False, False, 5.0)
    c.update_settings(volume=60)
    assert page.volume.value() == 60  # page follows external changes
    assert "#F1F4FA".lower() in qapp.styleSheet().lower()


def test_close_quits_without_tray(window, qapp, monkeypatch):
    w, c, _ = window
    quits = []
    monkeypatch.setattr("ui.main_window.QApplication.quit", lambda: quits.append(1))
    w.close()
    assert quits and w._quitting


def test_close_hides_to_tray_when_enabled(make_controller, qapp, monkeypatch):
    from ui.tray import TrayController
    from PySide6.QtWidgets import QSystemTrayIcon

    c = make_controller(ScriptedChecker(True))
    quits = []
    monkeypatch.setattr("ui.main_window.QApplication.quit", lambda: quits.append(1))
    tray = TrayController(c)
    monkeypatch.setattr(QSystemTrayIcon, "isVisible", lambda self: True)
    from ui.main_window import MainWindow

    w = MainWindow(c, tray)
    w.show()
    w.close()
    assert not w.isVisible() and not quits
    c.update_settings(minimize_to_tray_on_close=False)
    w.show()
    w.close()
    assert quits


def test_tray_menu_reflects_and_controls_state(make_controller, qapp):
    from ui.tray import TrayController

    checker = ScriptedChecker(True)
    c = make_controller(checker)
    c.monitor.set_interval(0.03)
    tray = TrayController(c)
    c.start()
    texts = [a.text() for a in tray.menu.actions() if a.text()]
    assert texts == ["Show Net Watcher", "Pause Monitoring", "Disable Sounds", "Exit"]

    assert wait_until(lambda: c.state is S.ONLINE, app=qapp)
    assert "Online" in tray.icon.toolTip()
    tray.pause_action.trigger()
    assert c.paused and tray.pause_action.text() == "Resume Monitoring"
    assert "paused" in tray.icon.toolTip()
    tray.sound_action.trigger()
    assert not c.settings.sounds_enabled and tray.sound_action.text() == "Enable Sounds"
    tray.pause_action.trigger()
    checker.reachable = False
    assert wait_until(lambda: c.state is S.OFFLINE, app=qapp)
    assert "DISCONNECTED" in tray.icon.toolTip()
    shown, quit_ = [], []
    tray.show_requested.connect(lambda: shown.append(1))
    tray.quit_requested.connect(lambda: quit_.append(1))
    tray.show_action.trigger()
    tray.quit_action.trigger()
    assert shown and quit_


def test_update_banner_dialog_and_settings_status(make_controller, qapp, tmp_path):
    from services import update_service as us
    from services.update_service import UpdateService
    from tests.test_update_service import FakeClient, make_info
    from ui.update_dialog import UpdateDialog

    c = make_controller(ScriptedChecker(True))
    updater = UpdateService(c, client=FakeClient(make_info()), current_version="1.0.0", downloads_dir=tmp_path / "u", launcher=lambda p: None)
    w, _ = build_main_window(c, with_tray=False, updater=updater)
    w.show()
    assert w.update_banner.isHidden()
    assert "Version 1.0.0" in w.version_label.text()

    w.settings_page.check_updates_button.click()
    assert wait_until(lambda: updater.state == us.AVAILABLE, app=qapp)
    assert not w.update_banner.isHidden() and "1.1.0" in w.update_label.text()
    assert w._update_dialog is not None and w._update_dialog.isVisible()  # manual check opens the dialog
    dialog: UpdateDialog = w._update_dialog
    assert "1.1.0" in dialog.title.text() and dialog.primary.text() == "Download and install"
    assert dialog.skip_button.isVisible()
    assert "1.1.0" in w.settings_page.update_status.text()

    updater._set_state(us.READY)
    assert dialog.primary.text() == "Install and restart" and not dialog.progress.isVisible()
    updater._set_state(us.DOWNLOADING)
    assert dialog.primary.text() == "Cancel download" and dialog.progress.isVisible()
    assert "ready" not in w.update_label.text() and "Downloading" in w.update_label.text()

    updater.state = us.AVAILABLE
    dialog.skip_button.click()
    assert updater.state == us.IDLE and w.update_banner.isHidden()
    dialog.close()
    w.hide()


def test_settings_page_without_updater_has_no_updates_section(window):
    w, _, _ = window
    assert w.updater is None and w.settings_page.updater is None
    assert w.update_banner.isHidden()
