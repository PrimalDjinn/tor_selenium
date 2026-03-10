"""Parallel session management."""

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Callable, Iterator

from puppets.session import Session
from puppets.exceptions import PuppetsError

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages multiple parallel browser sessions.

    This class handles running multiple sessions concurrently using
    thread pools. Each session gets its own Tor instance and browser.

    The SessionManager can:
    - Accept Session instances created by the user
    - Create new sessions programmatically
    - Run sessions in parallel
    - Execute actions on all session drivers

    Attributes:
        max_workers: Maximum number of parallel sessions.
        headless: Whether to run browsers in headless mode.
        tor_timeout: Timeout for Tor startup per session.
        sessions: List of Session instances being managed.
    """

    def __init__(
        self,
        max_workers: int = 10,
        headless: bool = False,
        tor_timeout: int = 120,
    ):
        """Initialize the session manager.

        Args:
            max_workers: Maximum number of parallel sessions.
            headless: Whether to run browsers in headless mode.
            tor_timeout: Timeout for Tor startup per session.
        """
        self.max_workers = max_workers
        self.headless = headless
        self.tor_timeout = tor_timeout
        self.sessions: List[Session] = []

    def __repr__(self) -> str:
        started = sum(1 for s in self.sessions if s.driver is not None)
        return (
            f"SessionManager(sessions={len(self.sessions)}, "
            f"started={started}, max_workers={self.max_workers})"
        )

    def __len__(self) -> int:
        """Return the number of managed sessions."""
        return len(self.sessions)

    def __iter__(self) -> Iterator[Session]:
        """Iterate over managed sessions."""
        return iter(self.sessions)

    def create_session(self, session_id: Optional[str] = None, **kwargs) -> Session:
        """Create a new Session and add it to the manager.

        Args:
            session_id: Optional custom session ID.
            **kwargs: Additional arguments passed to Session constructor.
                Supported keys: ``headless``, ``tor_timeout``,
                ``flags``, and ``browser_start_timeout``.

        Returns:
            The created Session instance.
        """
        session = Session(
            session_id=session_id,
            headless=kwargs.get("headless", self.headless),
            tor_timeout=kwargs.get("tor_timeout", self.tor_timeout),
            flags=kwargs.get("flags"),
            browser_start_timeout=kwargs.get("browser_start_timeout", 30),
        )
        self.sessions.append(session)
        return session

    def add_session(self, session: Session) -> None:
        """Add an existing Session to the manager.

        Args:
            session: A Session instance to manage.
        """
        self.sessions.append(session)

    def remove_session(self, session: Session) -> None:
        """Remove a Session from the manager.

        Note: This does NOT cleanup the session - call session.cleanup() first.

        Args:
            session: A Session instance to remove.
        """
        if session in self.sessions:
            self.sessions.remove(session)

    def clear_sessions(self) -> None:
        """Clear all sessions from the manager without cleaning them up."""
        self.sessions.clear()

    def start_all(self) -> List[Session]:
        """Start all managed sessions (Tor + browser) in parallel.

        Returns:
            List of sessions that failed to start. An empty list means
            all sessions started successfully.
        """
        logger.info(
            f"Starting {len(self.sessions)} sessions with {self.max_workers} workers"
        )

        failed: List[Session] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._start_session, s): s for s in self.sessions
            }

            for future in as_completed(futures):
                session = futures[future]
                try:
                    future.result()
                    logger.info(f"[{session.session_id}] Started successfully")
                except Exception as exc:
                    logger.error(f"[{session.session_id}] Failed to start: {exc}")
                    failed.append(session)

        return failed

    def _start_session(self, session: Session) -> None:
        """Internal method to start a single session."""
        session.start()

    def run_action(self, action: Callable[[Any], Any]) -> List[Dict[str, Any]]:
        """Run an action on all session drivers in parallel.

        Args:
            action: A callable that takes a WebDriver as its argument.
                The action will be run on each session's driver.

        Returns:
            List of result dictionaries with success status and any errors.

        Raises:
            PuppetsError: If any session has not been started (driver is None).
        """
        results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for session in self.sessions:
                future = executor.submit(self._run_action_on_session, session, action)
                futures[future] = session.session_id

            for future in as_completed(futures):
                session_id = futures[future]
                try:
                    result = future.result()
                    results.append(
                        {"session_id": session_id, "success": True, "result": result}
                    )
                except Exception as exc:
                    logger.error(f"Action failed for {session_id}: {exc}")
                    results.append(
                        {"session_id": session_id, "success": False, "error": str(exc)}
                    )

        return results

    def _run_action_on_session(
        self, session: Session, action: Callable[[Any], Any]
    ) -> Any:
        """Run an action on a single session's driver."""
        if session.driver is None:
            raise PuppetsError(
                f"Session {session.session_id!r} has no driver. "
                f"Call start_all() before run_action()."
            )
        return action(session.driver)

    def cleanup_all(self) -> None:
        """Cleanup all managed sessions.

        Stops all browsers and Tor instances, then clears the session list.
        """
        logger.info(f"Cleaning up {len(self.sessions)} sessions")

        for session in self.sessions:
            try:
                session.cleanup()
            except Exception as exc:
                logger.error(f"Error cleaning up session {session.session_id}: {exc}")

        self.sessions.clear()

    def run_sessions(
        self,
        num_sessions: int = 10,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Run multiple sessions in parallel.

        Creates new sessions, runs them, and returns results.
        For more control, use create_session()/add_session() and start_all().

        Args:
            num_sessions: Number of sessions to run.
            progress_callback: Optional callback(completed, total) for progress.

        Returns:
            List of result dictionaries, one per session.
        """
        results: List[Dict[str, Any]] = []
        completed = 0

        logger.info(f"Starting {num_sessions} sessions with {self.max_workers} workers")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all sessions
            futures = {}
            for i in range(num_sessions):
                session_id = f"session_{i+1}_{uuid.uuid4().hex[:6]}"
                session = Session(
                    session_id=session_id,
                    headless=self.headless,
                    tor_timeout=self.tor_timeout,
                    flags=kwargs.get("flags"),
                )
                future = executor.submit(session.run)
                futures[future] = session_id

            # Collect results as they complete
            for future in as_completed(futures):
                session_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    logger.error(f"Session {session_id} raised exception: {exc}")
                    results.append(
                        {
                            "session_id": session_id,
                            "success": False,
                            "error": str(exc),
                        }
                    )

                completed += 1
                if progress_callback:
                    progress_callback(completed, num_sessions)
                else:
                    logger.info(f"Completed {completed}/{num_sessions} sessions")

        # Summary
        successful = sum(1 for r in results if r.get("success", False))
        logger.info(f"All sessions completed: {successful}/{num_sessions} successful")

        return results

    def run_continuous(
        self,
        duration_seconds: int = 3600,
        interval_seconds: int = 10,
    ) -> List[Dict[str, Any]]:
        """Run sessions sequentially for a duration.

        Each session runs one at a time with a pause between them.
        For parallel execution, use run_sessions() or start_all() instead.

        Args:
            duration_seconds: Total time to run.
            interval_seconds: Time between session starts.

        Returns:
            List of all session results.
        """
        results: List[Dict[str, Any]] = []
        start_time = time.time()
        session_num = 0

        logger.info(f"Starting continuous mode for {duration_seconds} seconds")

        while time.time() - start_time < duration_seconds:
            session_num += 1
            session_id = f"continuous_{session_num}_{uuid.uuid4().hex[:6]}"

            logger.info(f"Starting session {session_num}...")
            session = Session(
                session_id=session_id,
                headless=self.headless,
                tor_timeout=self.tor_timeout,
            )
            try:
                result = session.run()
                results.append(result)
            except Exception as exc:
                results.append(
                    {
                        "session_id": session_id,
                        "success": False,
                        "error": str(exc),
                    }
                )

            # Wait before next session
            elapsed = time.time() - start_time
            if elapsed + interval_seconds < duration_seconds:
                time.sleep(interval_seconds)

        successful = sum(1 for r in results if r.get("success", False))
        logger.info(f"Continuous mode ended: {successful}/{len(results)} successful")

        return results
