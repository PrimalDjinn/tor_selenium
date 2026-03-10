"""Tests for load_test.metrics module."""

import socket
import threading
import logging
import time

import pytest

from load_test import metrics


def test_reuse_address_flag_set():
    """TCP server subclass should allow address reuse to avoid WinError 10048."""
    # the class attribute should be True
    assert hasattr(metrics, "ReusableTCPServer")
    assert metrics.ReusableTCPServer.allow_reuse_address is True


def test_start_file_server_port_conflict(caplog, monkeypatch):
    """If the underlying server raise an error, it is logged and swallowed."""
    caplog.set_level(logging.ERROR, logger="load_test.metrics")

    class FailingServer:
        def __init__(self, *args, **kwargs):
            raise OSError("[WinError 10048] address in use")

    monkeypatch.setattr(metrics, "ReusableTCPServer", FailingServer)

    # call function - the exception should be caught internally
    metrics.start_file_server(port=8001, directory=".")

    # give background thread (which tries to instantiate) a moment
    time.sleep(0.05)

    assert any("File server error" in rec.message for rec in caplog.records)


def test_start_metrics_server_port_conflict(caplog, monkeypatch):
    """Errors from start_http_server are logged instead of propagated."""
    caplog.set_level(logging.ERROR, logger="load_test.metrics")

    def fake_start(port):
        raise OSError("[WinError 10048] address in use")

    monkeypatch.setattr(metrics, "start_http_server", fake_start)

    metrics.start_metrics_server(port=8000)

    assert any("Failed to start Prometheus metrics server" in rec.message for rec in caplog.records)
