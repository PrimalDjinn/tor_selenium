"""Tests for browser module."""

import pytest
import platform
import shutil
import os
from unittest.mock import Mock, patch, MagicMock
from puppets.browser import Browser, detect_chrome_version
from puppets.exceptions import ChromeNotFoundError, BrowserError


class TestDetectChromeVersion:
    """Test detect_chrome_version function."""

    @patch("puppets.browser.subprocess.check_output")
    def test_detects_google_chrome(self, mock_check_output, monkeypatch):
        """Test detection of Google Chrome (non-Windows)."""
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(shutil, "which", lambda cmd: cmd)
        mock_check_output.return_value = b"Google Chrome 120.0.6099.109"
        version = detect_chrome_version()
        assert version == 120

    @patch("puppets.browser.subprocess.check_output")
    def test_detects_chromium(self, mock_check_output, monkeypatch):
        """Test detection of Chromium (non-Windows)."""
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(shutil, "which", lambda cmd: cmd)
        # First call raises FileNotFoundError, second returns chromium
        mock_check_output.side_effect = [
            FileNotFoundError(),
            b"Chromium 119.0.6045.124",
        ]
        version = detect_chrome_version()
        assert version == 119

    @patch("puppets.browser.subprocess.check_output")
    def test_returns_none_when_no_chrome(self, mock_check_output, monkeypatch):
        """Test returns None when no Chrome is found (non-Windows)."""
        monkeypatch.setattr(platform, "system", lambda: "Linux")
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        mock_check_output.side_effect = FileNotFoundError()
        version = detect_chrome_version()
        assert version is None

    @patch("puppets.browser.subprocess.check_output")
    def test_detects_chrome_on_windows(self, mock_check_output, monkeypatch):
        """Ensure detection works when running on Windows via binary lookup."""
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        # ensure which resolves so the loop tries the command
        monkeypatch.setattr(shutil, "which", lambda cmd: cmd)
        mock_check_output.return_value = b"Google Chrome 120.0.6099.109"
        version = detect_chrome_version()
        assert version == 120

    @patch("puppets.browser.subprocess.check_output")
    def test_windows_running_chrome_uses_registry(self, mock_check_output, monkeypatch):
        """If invoking the binary returns the "opening" message, fallback to registry."""
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        monkeypatch.setattr(shutil, "which", lambda cmd: cmd)
        # binary output that lacks a version number
        mock_check_output.return_value = b"Opening in existing browser session."
        # mock registry function to return version
        monkeypatch.setattr(
            'puppets.browser._read_chrome_version_from_registry',
            lambda: 123,
        )
        version = detect_chrome_version()
        assert version == 123

    def test_registry_lookup_only(self, monkeypatch):
        """Registry reader returns value even if no executables are present."""
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        # ensure absolute path check fails as well
        monkeypatch.setattr(os.path, "exists", lambda p: False)
        monkeypatch.setattr(
            'puppets.browser._read_chrome_version_from_registry',
            lambda: 88,
        )
        version = detect_chrome_version()
        assert version == 88

    @patch("puppets.browser.subprocess.check_output")
    def test_windows_no_chrome(self, mock_check_output, monkeypatch):
        """Return None on Windows when no browser is installed."""
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        monkeypatch.setattr(shutil, "which", lambda cmd: None)
        monkeypatch.setattr(
            'puppets.browser._read_chrome_version_from_registry',
            lambda: None,
        )
        mock_check_output.side_effect = FileNotFoundError()
        version = detect_chrome_version()
        assert version is None


class TestBrowser:
    """Test Browser class."""

    def test_browser_initialization(self):
        """Test Browser initializes with correct values."""
        browser = Browser(socks_port=9050)
        assert browser.socks_port == 9050
        assert browser.driver is None

    def test_browser_headless_option(self):
        """Test Browser accepts headless option."""
        browser = Browser(socks_port=9050, headless=True)
        assert browser.headless is True

    @patch("puppets.browser.detect_chrome_version")
    def test_browser_raises_when_no_chrome(self, mock_detect):
        """Test Browser raises ChromeNotFoundError when no Chrome."""
        mock_detect.return_value = None

        browser = Browser(socks_port=9050)

        with pytest.raises(ChromeNotFoundError):
            browser.start()

    @patch("puppets.browser.uc.Chrome")
    @patch("puppets.browser.detect_chrome_version")
    def test_browser_start(self, mock_detect, mock_chrome):
        """Test Browser.start() creates driver."""
        mock_detect.return_value = 120
        mock_driver = Mock()
        mock_chrome.return_value = mock_driver

        browser = Browser(socks_port=9050)
        driver = browser.start()

        assert driver is mock_driver
        assert browser.driver is mock_driver

    def test_browser_stop(self):
        """Test Browser.stop() quits driver."""
        browser = Browser(socks_port=9050)
        mock_driver = Mock()
        browser.driver = mock_driver

        browser.stop()

        mock_driver.quit.assert_called_once()
        assert browser.driver is None

    @patch("puppets.browser.uc.Chrome")
    @patch("puppets.browser.detect_chrome_version")
    def test_browser_context_manager(self, mock_detect, mock_chrome):
        """Test Browser as context manager."""
        mock_detect.return_value = 120
        mock_driver = Mock()
        mock_chrome.return_value = mock_driver

        with Browser(socks_port=9050) as browser:
            assert browser.driver is not None

        mock_driver.quit.assert_called_once()
