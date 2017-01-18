# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import requests

from generic_test_code import (
    generic_correct_upstream_dest_test,
    generic_correct_upstream_request_test,
    generic_upstream_headers_verify_test,
)


class TestExhibitorEndpoint():
    def test_if_exhibitor_endpoint_redirects_req_without_slash(
            self, master_ar_process):
        url = master_ar_process.make_url_from_path("/exhibitor")
        r = requests.get(url, allow_redirects=False)

        assert r.status_code == 301

    def test_if_exhibitor_endpoint_handles_redirects_properly(
            self, master_ar_process, mocker, valid_user_header):
        location_sent = 'http://127.0.0.1/exhibitor/v1/ui/index.html'
        location_expected = 'http://127.0.0.1/exhibitor/exhibitor/v1/ui/index.html'
        mocker.send_command(endpoint_id='http://127.0.0.1:8181',
                            func_name='always_redirect',
                            aux_data=location_sent)

        url = master_ar_process.make_url_from_path("/exhibitor/v1/ui/index.html")
        r = requests.get(url, allow_redirects=False, headers=valid_user_header)

        assert r.status_code == 307
        assert r.headers['Location'] == location_expected

    def test_if_request_is_sent_to_correct_upstream(self,
                                                    master_ar_process,
                                                    valid_user_header):

        generic_correct_upstream_dest_test(master_ar_process,
                                           valid_user_header,
                                           '/exhibitor/some/path',
                                           'http://127.0.0.1:8181',
                                           )

    def test_if_upstream_request_is_correct(self,
                                            master_ar_process,
                                            valid_user_header):

        generic_correct_upstream_request_test(master_ar_process,
                                              valid_user_header,
                                              '/exhibitor/some/path',
                                              '/some/path',
                                              )

    def test_if_upstream_headers_are_correct(self,
                                             master_ar_process,
                                             valid_user_header):

        generic_upstream_headers_verify_test(master_ar_process,
                                             valid_user_header,
                                             '/exhibitor/some/path',
                                             )
