# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging
import requests


log = logging.getLogger(__name__)


def generic_unknown_user_is_forbidden_test(ar, auth_header, path):
    url = ar.make_url_from_path(path)
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header)

    assert resp.status_code == 401


def generic_valid_user_is_permited_test(ar, auth_header, path):
    url = ar.make_url_from_path(path)
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header)

    assert resp.status_code == 200


def generic_upstream_headers_verify_test(ar, auth_header, path):
    url = ar.make_url_from_path('/exhibitor/some/path')
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header)

    assert resp.status_code == 200

    req_data = resp.json()
    verify_header(req_data['headers'], 'Host', '127.0.0.1')
    verify_header(req_data['headers'], 'X-Forwarded-For', '127.0.0.1')
    verify_header(req_data['headers'], 'X-Forwarded-Proto', 'http')
    verify_header(req_data['headers'], 'X-Real-IP', '127.0.0.1')


def generic_correct_upstream_dest_test(ar, auth_header, path, endpoint_id):
    url = ar.make_url_from_path(path)
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header)

    assert resp.status_code == 200
    req_data = resp.json()
    assert req_data['endpoint_id'] == endpoint_id


def generic_correct_upstream_request_test(
        ar, auth_header, given_path, expected_path, http_ver='HTTP/1.0'):
    url = ar.make_url_from_path(given_path)
    resp = requests.get(url,
                        allow_redirects=False,
                        headers=auth_header)

    assert resp.status_code == 200
    req_data = resp.json()
    assert req_data['method'] == 'GET'
    assert req_data['path'] == expected_path
    assert req_data['request_version'] == http_ver


def verify_header(headers, header_name, header_value):
    """Asserts that particular header exists and has correct value.

    Helper function for checking if header with given name has been defined
    with correct value in given headers list. The headers list is in format
    defined by requests module.

    Presence of more than one header with given name or incorrect value raises
    assert statement.

    Args:
        header_name (str): header name to seek
        header_value (str): expected value of the header
        headers (obj: [('h1', 'v1'), ('h2', 'v2'), ...]): a list of header
            name-val tuples

    Raises:
        AssertionError: header has not been found, there is more than one header
            with given name or header has incorrect value
    """
    mathing_headers = list()

    for header in headers:
        if header[0] == header_name:
            mathing_headers.append(header)

    # Hmmm....
    if len(mathing_headers) != 1:
        if len(mathing_headers) == 0:
            msg = "Header `{}` has not been found".format(header_name)
        elif len(mathing_headers) > 1:
            msg = "More than one `{}` header has been found".format(header_name)

        assert len(mathing_headers) == 1, msg

    assert mathing_headers[0][1] == header_value
