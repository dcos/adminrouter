# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""This module provides a set of helper functions for tests.

    Attributes:
        LOG_LINE_SEARCH_INTERVAL (decimal): Defines (in seconds), intervals
            between subsequent scans of log buffers.
"""

import code
import logging
import pyroute2
import signal
import time
import traceback


LOG_LINE_SEARCH_INTERVAL = 0.2

log = logging.getLogger(__name__)


class LineBufferFilter():
    """Helper class for grokking line buffers created by LogCatcher class

    This class is meant to simplify searching of particular strings in line
    buffers created by LogCatcher object for subprocess run by this test
    harness.

    It exposes two interfaces:
    * context manager interface for isolating logs from particular event, i.e.
        lbf = LineBufferFilter(filter_string,
                               line_buffer=ar_process.stderr_line_buffer)

        with lbf:
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=header)

        assert lbf.log_line_found

        In this case log buffer will be scanned only for entries that were added
        while executing the `requests.get()` call.

    * `.scan_log_buffer()` approach in case string should be searched from the
        begining of the log.

        lbf = LineBufferFilter(filter_string,
                               line_buffer=ar_process.stderr_line_buffer)

        lbf.scan_log_buffer()

        assert lbf.log_line_found is True

    The result - whether the log was found or not can be determined using
    `log_line_found` attribute.
    """
    _filter_string = None
    _line_buffer = None
    _line_buffer_start = None
    _timeout = None
    _log_line_found = None

    def __init__(self, filter_string, line_buffer, timeout=3):
        """Initialize new LineBufferFilter object

        Create new LineBufferFilter object configured to search for string
        `filter_string` in line buffer `filter_string` for as much as `timeout`
        seconds.

        Args:
            filter_string (str): string that the instance should look for in the logs,
              using a plain matching/no regexpes.
            line_buffer (list()): an array of log lines, as presented by `.*_line_buffer()`
              method of the object we want to scan lines for.
            timeout (int): how long before LineBufferFilter gives up on searching for
              filter_string in line_buffer
        """
        assert isinstance(timeout, int)
        assert timeout >= LOG_LINE_SEARCH_INTERVAL
        assert isinstance(line_buffer, list)

        self._filter_string = filter_string
        self._line_buffer = line_buffer
        self._timeout = timeout

    def __enter__(self):
        assert self._line_buffer_start is None
        assert self._line_buffer is not None

        self._line_buffer_start = len(self._line_buffer)

    def scan_log_buffer(self):
        """Scan for `filter_string` since the beginning of the given instance's log

        This is a convenience function that forces search of the `filter_string`
        since the begining of the log buffer. It's does by simply fixing the
        start position and calling the __exit__() method of the context manager
        """
        # Bit hacky, but good enough™
        self._line_buffer_start = 0
        self.__exit__()

    def __exit__(self, *unused):
        """Context manager __exit__ method for filter string search

        This is the heart of the LineBufferFilter - the whole matching happens
        here.
        """
        assert self._log_line_found is None

        msg_fmt = "Beginning to scan for line `%s` in logline buffer"
        log.debug(msg_fmt, self._filter_string)

        deadline = time.time() + self._timeout
        self._log_line_found = False

        while time.time() < deadline and not self._log_line_found:
            lines_scanned = 0

            for log_line in self._line_buffer[self._line_buffer_start:]:
                if self._filter_string in log_line:
                    self._log_line_found = True
                    return
                lines_scanned += 1

            self._line_buffer_start = self._line_buffer_start + lines_scanned

            msg_fmt = "waiting for line `%s` to appear in logline buffer"
            log.debug(msg_fmt, self._filter_string)

            time.sleep(LOG_LINE_SEARCH_INTERVAL)

        msg_fmt = "Timed out while waiting for line `%s` to appear in logline buffer"
        log.debug(msg_fmt, self._filter_string)

    @property
    def log_line_found(self):
        """Check if LineBufferFilter found the string in the logs

        Returns:
            True/False, depending whether the string was found or not.
        """
        assert self._log_line_found is not None

        return self._log_line_found


def configure_logger(pytest_config):
    """ Set up a logging basing on pytest cmd line args.

    Configure log verbosity basing on the --log-level command line
    argument (INFO by default).
    """

    tests_log_level = pytest_config.getoption('tests_log_level')
    rootlogger = logging.getLogger()

    # Set up a stderr handler for the root logger, and specify the format.
    fmt = "%(asctime)s.%(msecs)03d %(name)s:%(lineno)s %(levelname)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt="%y%m%d-%H:%M:%S"
        )

    if tests_log_level != 'disabled':
        level = getattr(logging, tests_log_level.upper())
        rootlogger.setLevel(level)
    else:
        rootlogger.handlers = []
        rootlogger.addHandler(logging.NullHandler())


def add_lo_ipaddr(ip_addr, prefix_len):
    """Add an ipv4 address to loopback interface.

    Add an ipv4 address to loopback provided that it does not already exist.

    Args:
        ip_addr (str): IP address
        prefix_len (int): prefix length
    """
    iproute2 = pyroute2.IPRoute()
    idx = iproute2.link_lookup(ifname='lo')[0]

    existing_ips = iproute2.get_addr(index=idx)
    for existing_ip in existing_ips:
        if existing_ip['family'] != 2:
            # Only support only ipv4 for now, so this one is not ours
            continue

        if existing_ip['prefixlen'] != prefix_len:
            # Not ours, but yes - same IP with different prefix will bork
            # things up. But this should not happen during normal OP.
            continue

        for attr in existing_ip['attrs']:
            if attr[0] == "IFA_ADDRESS" and attr[1] == ip_addr:
                msg_fmt = "Not adding addres `%s/%s`` as it already exists`"
                log.info(msg_fmt, ip_addr, prefix_len)
                return

    iproute2.addr('add', index=idx, address=ip_addr, mask=prefix_len)


def del_lo_ipaddr(ip_addr, prefix_len):
    """Remove ipv4 address from loopback interface

    Remove existing ipv4 address, defined by ip_addr and prefix_len, from
    loopback interface.

    Args:
        ip_addr (str): IP address
        prefix_len (int): prefix length

    Raises:
        NetlinkError: failed to remove address, check exception data for details.
    """
    iproute2 = pyroute2.IPRoute()
    idx = iproute2.link_lookup(ifname='lo')[0]
    iproute2.addr('del', index=idx, address=ip_addr, mask=prefix_len)


def setup_thread_debugger():
    """Setup a thread debbuger for pytest session

    This function, based on http://stackoverflow.com/a/133384, is meant to
    add debugging facility to pytest that will allow to debug deadlock that
    may sometimes occur.
    """
    def debug(signal, frame):
        """Interrupt running process and provide a python prompt for
        interactive debugging."""
        d = {'_frame': frame}  # Allow access to frame object.
        d.update(frame.f_globals)  # Unless shadowed by global
        d.update(frame.f_locals)

        i = code.InteractiveConsole(d)
        message = "Signal received : entering python shell.\nTraceback:\n"
        message += ''.join(traceback.format_stack(frame))
        i.interact(message)

    signal.signal(signal.SIGUSR1, debug)  # Register handler
