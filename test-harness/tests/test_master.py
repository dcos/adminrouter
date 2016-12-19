# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import requests


class TestExhibitorEndpoint():
    def test_if_exhibitor_endpoint_redirects_without_slash(self,
                                                           master_ar_process):
        url = master_ar_process.make_url_from_path("/exhibitor")
        r = requests.get(url, allow_redirects=False)

        assert r.status_code == 301
