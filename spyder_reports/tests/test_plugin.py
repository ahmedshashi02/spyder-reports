# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
#
"""Tests for the plugin."""

# Third party imports
import pytest
import os
import os.path as osp

# Spyder-IDE and Local imports
from spyder.utils.programs import TEMPDIR
from spyder_reports.reportsplugin import ReportsPlugin


@pytest.fixture
def setup_reports(qtbot, monkeypatch):
    """Set up the Reports plugin."""
    monkeypatch.setattr(
            'spyder_reports.reportsplugin.ReportsPlugin.initialize_plugin',
            lambda self: None)
    reports = ReportsPlugin(None)
    qtbot.addWidget(reports)
    reports.show()
    return reports


@pytest.fixture(scope='session', params=['mdw', 'md'])
def report_file(request, tmpdir_factory):
    """
    Fixture for create a temporary report file.

    Returns:
        str: Path of temporary report file.
    """
    report_file = tmpdir_factory.mktemp('data').join(
            "'test_report.{}".format(request.param))
    report_file.write('# This is a Markdown report')
    return str(report_file)


def test_basic_initialization(qtbot, setup_reports):
    """Test Reports plugin initialization."""
    reports = setup_reports

    # Assert that reports exist
    assert reports is not None


def test_basic_render(qtbot, report_file, setup_reports):
    """Test rendering of an basic .mdw report returning a .html file."""
    reports = setup_reports
    output_file = reports._render_report(report_file)

    # Assert that output_file is an html file
    assert output_file.split('.')[-1] == 'html'


def test_check_compability(qtbot, setup_reports, monkeypatch):
    """Test state and message returned by check_compatibility."""
    monkeypatch.setattr('spyder_reports.reportsplugin.PYQT4', True)
    monkeypatch.setattr('spyder_reports.reportsplugin.PY3', False)

    reports = setup_reports

    valid, message = reports.check_compatibility()
    assert not valid
    assert 'qt4' in message.lower()
    assert 'python2' in message.lower()


def test_get_plugin_actions(qtbot, setup_reports):
    """Test get plugin actions method."""
    reports = setup_reports

    class MainMock():
        run_menu_actions = []

    # patch reports object with mock MainWindow
    reports.main = MainMock()

    menu_actions = reports.get_plugin_actions()

    assert len(menu_actions) == 3
    assert "Render report to HTML" in menu_actions[0].text()
    assert "Save Report" in menu_actions[1].text()
    assert "Save Report as" in menu_actions[2].text()

    assert "Render report to HTML" in reports.main.run_menu_actions[0].text()


def test_run_reports_render(qtbot, setup_reports, report_file):
    """Test rendering a report when calling it from menu entry."""
    reports = setup_reports

    class EditorStackMock():
        def save(self):
            return True

    class EditorMock():
        def get_current_editorstack(self):
            return EditorStackMock()

        def get_current_filename(self):
            return report_file

    class MainMock():
        editor = EditorMock()

    def switch_to_plugin():
        pass

    # patch reports object with mock MainWindow
    reports.main = MainMock()
    reports.switch_to_plugin = switch_to_plugin

    with qtbot.waitSignal(reports.sig_render_finished, timeout=5000) as sig:
        reports.run_reports_render()

    ok, filename, error = sig.args
    assert ok
    assert error is None
    assert osp.exists(filename)

    renderview = reports.report_widget.renderviews.get(report_file)
    assert renderview is not None


def test_render_report_thread(qtbot, setup_reports, report_file):
    """Test rendering report in a worker thread."""
    reports = setup_reports

    with qtbot.waitSignal(reports.sig_render_finished, timeout=5000) as sig:
        with qtbot.waitSignal(reports.sig_render_started):
            reports.render_report_thread(report_file)

        # Assert that progress bar was shown
        assert reports.report_widget.progress_bar.isVisible()
        assert 'Rendering' in reports.report_widget.status_text.text()

    ok, filename, error = sig.args
    assert ok
    assert error is None
    assert osp.exists(filename)

    # Assert that progress bar was hidden
    assert not reports.report_widget.progress_bar.isVisible()

    renderview = reports.report_widget.renderviews.get(report_file)
    assert renderview is not None


def test_render_report_thread_error(qtbot, setup_reports):
    """Test rendering report in a worker thread."""
    reports = setup_reports

    with qtbot.waitSignal(reports.sig_render_finished, timeout=5000) as sig:
        reports.render_report_thread('file_that_doesnt_exist.mdw')

    ok, filename, error = sig.args
    assert not ok
    assert "[Errno 2]" in error
    assert filename == 'file_that_doesnt_exist.mdw'

    def tab_closed():
        assert reports.report_widget.tabs.count() == 0

    qtbot.waitUntil(tab_closed)
    for renderview in reports.report_widget.renderviews:
        assert 'file_that_doesnt_exist' not in renderview

    # Assert that progress bar shows the error
    assert reports.report_widget.progress_bar.isVisible()
    assert error in reports.report_widget.status_text.text()


def test_render_report_thread_not_supported(qtbot, setup_reports,
                                            tmpdir_factory):
    """Test rendering report in a worker thread."""
    reports = setup_reports

    python_file = tmpdir_factory.mktemp('data').join("'test_report.py")
    python_file.write('# This is a python file')
    python_file = str(python_file)

    with qtbot.waitSignal(reports.sig_render_finished, timeout=5000) as sig:
        reports.render_report_thread(python_file)

    ok, filename, error = sig.args
    assert not ok
    assert "Format not supported (.py)" in error
    assert filename == python_file

    def tab_closed():
        assert reports.report_widget.tabs.count() == 0

    qtbot.waitUntil(tab_closed)
    for renderview in reports.report_widget.renderviews:
        assert python_file not in renderview

    # Assert that progress bar shows the error
    assert reports.report_widget.progress_bar.isVisible()
    assert error in reports.report_widget.status_text.text()


def test_render_tmp_dir(qtbot, setup_reports, report_file):
    """Test that rendered files are created in spyder's tempdir."""
    reports = setup_reports
    output_file = reports._render_report(report_file)

    # Test that outfile is in spyder tmp dir
    assert osp.samefile(osp.commonprefix([output_file, TEMPDIR]), TEMPDIR)


def test_render_same_file(qtbot, setup_reports, report_file):
    """Test that re-rendered files are created in the same tempdir."""
    reports = setup_reports

    output_file1 = reports._render_report(report_file)
    output_file2 = reports._render_report(report_file)

    assert osp.exists(output_file2)
    # Assert that file has been re-rendered in the same path
    assert osp.samefile(output_file1, output_file2)


def test_save_report(qtbot, tmpdir_factory, setup_reports, report_file,
                     monkeypatch):
    """Test saving a report.

    Test copying from tempdir to an user selected location.
    """
    reports = setup_reports

    with qtbot.waitSignal(reports.sig_render_finished, timeout=5000) as sig:
        reports.render_report_thread(report_file)

    ok, filename, error = sig.args
    assert ok
    assert error is None
    assert osp.exists(filename)

    folder, _ = osp.split(filename)
    save_folder = str(tmpdir_factory.mktemp('data2'))

    monkeypatch.setattr('spyder_reports.reportsplugin.getexistingdirectory',
                        lambda *args, **kwargs: save_folder)

    reports.save_report()

    assert set(os.listdir(folder)) == set(os.listdir(save_folder))

    # Saving again shouldn't call getexistingdirectory
    monkeypatch.setattr('spyder_reports.reportsplugin.getexistingdirectory',
                        lambda *args, **kwargs: exec('raise(Exception())'))
    reports.save_report()


def test_save_no_report(setup_reports):
    """Test save report when no report is open.

    Should do nothing, but shouldn't raise an error.
    """
    reports = setup_reports
    reports.report_widget.get_focus_report = lambda: None

    reports.save_report()


if __name__ == "__main__":
    pytest.main()
