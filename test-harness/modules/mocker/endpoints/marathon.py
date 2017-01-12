# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""Marathon mock endpoint"""

import logging

from exceptions import EndpointException
from mocker.endpoints.recording import (
    RecordingHTTPRequestHandler,
    RecordingTcpIpEndpoint,
)

# pylint: disable=C0103
log = logging.getLogger(__name__)


# pylint: disable=R0903
class MarathonHTTPRequestHandler(RecordingHTTPRequestHandler):
    """A very simple request handler that simply replies with static(empty) list
       of applications to the client

    Most probably it will be extended with some extra logic as tests are
    being added.
    """
    def _calculate_response(self, base_path, *_):
        """Reply with empty list of apps for the '/v2/apps' request

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments and return value of this method.

        Raises:
            EndpointException: request URL path is unsupported
        """
        if base_path != '/v2/apps':
            msg = "Path `{}` is not supported yet".format(base_path)
            blob = msg.encode('utf-8')
            raise EndpointException(code=500, reason=blob)
        res = {"apps": []}

        blob = self._convert_data_to_blob(res)

        return blob


# pylint: disable=R0903,C0103
class MarathonEndpoint(RecordingTcpIpEndpoint):
    """An endpoint that mimics DC/OS root Marathon"""
    def __init__(self, port, ip=''):
        super().__init__(port, ip, MarathonHTTPRequestHandler)
