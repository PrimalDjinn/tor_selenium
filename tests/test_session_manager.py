"""Tests for session manager module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from puppets.session_manager import SessionManager
from puppets.session import Session
from puppets.exceptions import PuppetsError


class TestSessionManagerInit:
    """Test SessionManager initialization."""

    def test_default_initialization(self):
        """Test SessionManager initializes with default values."""
        manager = SessionManager()
        assert manager.max_workers == 10
        assert manager.headless is False
        assert manager.tor_timeout == 120
        assert manager.sessions == []

    def test_custom_initialization(self):
        """Test SessionManager accepts custom values."""
        manager = SessionManager(max_workers=5, headless=True, tor_timeout=60)
        assert manager.max_workers == 5
        assert manager.headless is True
        assert manager.tor_timeout == 60


class TestSessionManagerDunders:
    """Test dunder methods."""

    def test_repr(self):
        """Test __repr__ output."""
        manager = SessionManager(max_workers=5)
        assert "SessionManager" in repr(manager)
        assert "sessions=0" in repr(manager)
        assert "max_workers=5" in repr(manager)

    def test_len_empty(self):
        """Test __len__ with no sessions."""
        manager = SessionManager()
        assert len(manager) == 0

    def test_len_with_sessions(self):
        """Test __len__ with added sessions."""
        manager = SessionManager()
        manager.add_session(Session(session_id="s1"))
        manager.add_session(Session(session_id="s2"))
        assert len(manager) == 2

    def test_iter(self):
        """Test __iter__ over sessions."""
        manager = SessionManager()
        s1 = Session(session_id="s1")
        s2 = Session(session_id="s2")
        manager.add_session(s1)
        manager.add_session(s2)

        sessions = list(manager)
        assert sessions == [s1, s2]


class TestSessionManagement:
    """Test session add/remove/create/clear operations."""

    def test_create_session(self):
        """Test create_session adds to manager."""
        manager = SessionManager()
        session = manager.create_session(session_id="test")
        assert len(manager.sessions) == 1
        assert session.session_id == "test"
        assert session is manager.sessions[0]

    def test_create_session_inherits_defaults(self):
        """Test create_session uses manager defaults."""
        manager = SessionManager(headless=True, tor_timeout=60)
        session = manager.create_session()
        assert session.headless is True
        assert session.tor_timeout == 60

    def test_create_session_overrides(self):
        """Test create_session allows overriding manager defaults."""
        manager = SessionManager(headless=True)
        session = manager.create_session(headless=False)
        assert session.headless is False

    def test_create_session_browser_timeout(self):
        """Ensure browser_start_timeout can be passed through."""
        manager = SessionManager()
        session = manager.create_session(browser_start_timeout=77)
        assert session.browser_start_timeout == 77

    def test_add_session(self):
        """Test add_session appends to list."""
        manager = SessionManager()
        session = Session(session_id="ext")
        manager.add_session(session)
        assert session in manager.sessions

    def test_remove_session(self):
        """Test remove_session removes from list."""
        manager = SessionManager()
        session = Session(session_id="rm")
        manager.add_session(session)
        manager.remove_session(session)
        assert session not in manager.sessions

    def test_remove_nonexistent_session(self):
        """Test remove_session with unknown session is a no-op."""
        manager = SessionManager()
        session = Session(session_id="ghost")
        manager.remove_session(session)  # Should not raise
        assert len(manager.sessions) == 0

    def test_clear_sessions(self):
        """Test clear_sessions empties the list."""
        manager = SessionManager()
        manager.add_session(Session())
        manager.add_session(Session())
        manager.clear_sessions()
        assert len(manager.sessions) == 0


class TestCleanupAll:
    """Test cleanup_all behavior."""

    def test_cleanup_all_calls_cleanup_on_each(self):
        """Test cleanup_all calls cleanup on all sessions."""
        manager = SessionManager()
        s1 = Mock(spec=Session)
        s1.session_id = "s1"
        s2 = Mock(spec=Session)
        s2.session_id = "s2"
        manager.sessions = [s1, s2]

        manager.cleanup_all()

        s1.cleanup.assert_called_once()
        s2.cleanup.assert_called_once()
        assert len(manager.sessions) == 0

    def test_cleanup_all_handles_errors(self):
        """Test cleanup_all continues on individual failure."""
        manager = SessionManager()
        s1 = Mock(spec=Session)
        s1.session_id = "s1"
        s1.cleanup.side_effect = Exception("cleanup failed")
        s2 = Mock(spec=Session)
        s2.session_id = "s2"
        manager.sessions = [s1, s2]

        manager.cleanup_all()

        # Both should be attempted
        s1.cleanup.assert_called_once()
        s2.cleanup.assert_called_once()
        assert len(manager.sessions) == 0


class TestRunAction:
    """Test run_action behavior."""

    def test_run_action_with_none_driver(self):
        """Test run_action raises helpful error for unstarted session."""
        manager = SessionManager()
        session = Session(session_id="nodriver")
        manager.add_session(session)

        results = manager.run_action(lambda driver: driver.get("https://example.com"))

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "no driver" in results[0]["error"].lower()

    def test_run_action_success(self):
        """Test run_action passes driver to callable."""
        manager = SessionManager()
        session = Session(session_id="ok")
        mock_driver = Mock()
        session._driver = mock_driver
        manager.add_session(session)

        results = manager.run_action(lambda driver: driver.title)

        assert len(results) == 1
        assert results[0]["success"] is True

    def test_run_action_handles_exceptions(self):
        """Test run_action catches action exceptions."""
        manager = SessionManager()
        session = Session(session_id="err")
        mock_driver = Mock()
        session._driver = mock_driver
        manager.add_session(session)

        def bad_action(driver):
            raise ValueError("boom")

        results = manager.run_action(bad_action)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "boom" in results[0]["error"]
