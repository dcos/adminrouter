# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""Module that defines the behaviour common to all requests handlers used by mocker.
"""

import abc
import http.server
import json
import logging
import socket
import traceback

from urllib.parse import parse_qs, urlparse

from exceptions import EndpointException

# pylint: disable=C0103
log = logging.getLogger(__name__)


class BaseHTTPRequestHandler(http.server.BaseHTTPRequestHandler,
                             metaclass=abc.ABCMeta):
    """HTTP request handler base class that implements all common behaviour
       shared across mocker's request handlers.
    """
    @abc.abstractmethod
    def _calculate_response(self, base_path, url_args, body_args=None):
        """Calculate response basing on the request arguments.

        Methods overriding it should return a response body that reflects
        requests arguments and path.

        Args:
            base_path (str): request's path without query parameters
            url_args (dict): a dictionary containing all the query arguments
                encoded in request path
            body_args (dict): a dictionary containing all the arguments encoded
                in the body of the request

        Returns:
            A bytes array, exactly as it should be send to the client.

        Raises:
            EndpointException: This exception signalizes that the normal
                processing of the request should be stopped, and the response
                with given status&content-encoding&body should be immediately
                sent.
        """
        pass

    @abc.abstractmethod
    def _parse_request_body(self):
        """Extract requests arguments encoded in it's body

        Methods overriding it should parse request body in a way that's
        suitable for given request handler.

        Returns:
            It depends on the request handler - it may be a dict, a string,
            or anything/nothing.

        Raises:
            EndpointException: This exception signalizes that the normal
                processing of the request should be stopped, and the response
                with given status&content-encoding&body should be immediately
                sent.
        """
        pass

    @abc.abstractmethod
    def _send_response(self, blob):
        """Send a response to the clients

        Methods overriding it should send the response in a way suitable for
        given base handler. For some it may be JSON, for others it may be just
        a plain text.

        Raises:
            EndpointException: This exception signalizes that the normal
                processing of the request should be stopped, and the response
                with given status&content-encoding&body should be immediately
                sent.
        """
        pass

    def log_message(self, log_format, *args):
        """Just a patch to make Mockers Requests Handlers compatible with
           Unix Sockets.

        Method logs the request without source IP address/with hard-coded value
        of `unix-socket-connection` if the socket is a Unix Socket.

        Please check the http.server.BaseHTTPRequestHandler documentation
        for the meaning of the function arguments.
        """
        if self.server.address_family == socket.AF_UNIX:
            log.debug("%s - - [%s] %s\n",
                      "unix-socket-connection",
                      self.log_date_time_string(),
                      log_format % args)
        else:
            log.debug("%s - - [%s] %s\n",
                      self.address_string(),
                      self.log_date_time_string(),
                      log_format % args)

    def _finalize_request(self, code, content_type, blob):
        """A helper function meant to abstract sending request to client

        Arguments:
            code (int): HTTP response code to send
            content_type (string): HTTP content type value of the response
            blob (b''): data to send to the client in the body of the request
        """
        self.send_response(code)
        self.send_header('Content-type', content_type)
        self.end_headers()

        self.wfile.write(blob)

    @staticmethod
    def _convert_data_to_blob(data):
        """A helper function meant to simplify converting python objects to
           bytes arrays.

        Arguments:
            data: data to convert to b''. Can be anything as long as it's JSON
                serializable.

        Returns:
            A resulting byte sequence
        """
        return json.dumps(data,
                          indent=4,
                          sort_keys=True,
                          ensure_ascii=False,
                          ).encode('utf-8',
                                   errors='backslashreplace')

    def _parse_request_path(self):
        """Parse query arguments in the request path to dict.

        Returns:
            A tuple that contains a request path stripped of query arguments
            and a dict containing all the query arguments (if any).
        """
        parsed_url = urlparse(self.path)
        path_component = parsed_url.path
        query_components = parse_qs(parsed_url.query)
        return path_component, query_components

    def _unified_method_handler(self):
        """A unified entry point for all request types.

        This method is meant to be top level entry point for all requests.
        This class specifies only GET|POST for now, but other handlers can
        add request types if necessary.

        All query parameters are extracted (both from the uri and the body),
        and the handlers self._calculate_response method is called to produce
        a correct response. Handlers may terminate this workflow by raising
        EndpointException if necessary. All other exceptions are also caught and
        apart from being logged, are also send to the client in order to
        make debugging potential problems easier and failures more explicit.
        """
        endpoint_id = self.server.context.data['endpoint_id']

        msg_fmt = "Endpoint `%s`, _unified_method_handler() starts"
        log.debug(msg_fmt, endpoint_id)

        try:
            path, url_args = self._parse_request_path()
            body_args = self._parse_request_body()
            blob = self._calculate_response(path, url_args, body_args)
        except EndpointException as e:
            self._finalize_request(e.code, e.content_type, e.reason)
        # Pylint, please trust me on this one ;)
        # pylint: disable=W0703
        except Exception:
            msg_fmt = ("Exception occurred while handling the request in "
                       "endpoint `%s`")
            log.exception(msg_fmt, endpoint_id)

            # traceback.format_exc() returns str, i.e. text, i.e. a sequence of
            # unicode code points. UTF-8 is a unicode-complete codec. That is,
            # any and all unicode code points can be encoded.
            blob = traceback.format_exc().encode('utf-8')
            self._finalize_request(500, 'text/plain; charset=utf-8', blob)
        else:
            self._send_response(blob)

    def do_GET(self):
        """Please check the http.server.BaseHTTPRequestHandler documentation
           for the method description.

        Worth noting is that GET request can also be a POST - can have both
        request path arguments and body arguments.
        http://stackoverflow.com/a/2064369
        """
        self._unified_method_handler()

    def do_POST(self):
        """Please check the http.server.BaseHTTPRequestHandler documentation
           for the method description.

        Worth noting is that GET request can also be a POST - can have both
        request path arguments and body arguments.
        http://stackoverflow.com/a/2064369
        """
        self._unified_method_handler()
