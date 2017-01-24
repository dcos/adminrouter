# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import logging
import requests
import time

from util import LineBufferFilter, SearchCriteria, GuardedAR
from runner.common import FIRST_POLL_DELAY
from mocker.endpoints.mesos import EXTRA_SLAVE_DICT

log = logging.getLogger(__name__)


def ping_agent_1(ar, jwt_data):
    url = ar.make_url_from_path(
        '/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/agent-1/blah/blah')

    resp = requests.get(url, allow_redirects=False, headers=jwt_data)

    assert resp.status_code == 200
    req_data = resp.json()
    assert req_data['endpoint_id'] == 'http://127.0.0.2:15001'


class TestCache():
    def test_if_first_cache_refresh_occurs_earlier(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Executing cache refresh triggered by timer': SearchCriteria(1, False),
            'Cache `[\s\w]+` empty. Fetching.': SearchCriteria(2, True),
            'Mesos state cache has been successfully updated': SearchCriteria(1, True),
            'Marathon apps cache has been successfully updated': SearchCriteria(1, True),
            }
        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')
        # Enable recording for mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        # Make regular polling occur later than usual, so that we get clear
        # results.
        ar = nginx_class(poll_period=60, cache_expiry=55)

        with GuardedAR(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)

            lbf.scan_log_buffer()

            # Do a request that uses cache so that we can verify that data was
            # in fact cached and no more than one req to mesos/marathon
            # backends were made
            ping_agent_1(ar, valid_user_header)

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')
        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        assert lbf.extra_matches == {}
        assert len(mesos_requests) == 1
        assert len(marathon_requests) == 2

    def test_if_cache_refresh_occurs_regularly(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Executing cache refresh triggered by timer': SearchCriteria(3, False),
            'Cache `[\s\w]+` expired. Refresh.': SearchCriteria(2, True),
            'Mesos state cache has been successfully updated': SearchCriteria(3, True),
            'Marathon apps cache has been successfully updated': SearchCriteria(3, True),
            }
        poll_period = 4

        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')
        # Enable recording for mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        # Make regular polling occur faster than usual to speed up the tests.
        ar = nginx_class(poll_period=poll_period, cache_expiry=3)

        # In total, we should get three cache updates in given time frame:
        timeout = FIRST_POLL_DELAY + poll_period * 2 + 1

        with GuardedAR(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=timeout,
                                   line_buffer=ar.stderr_line_buffer)

            lbf.scan_log_buffer()

            # Do a request that uses cache so that we can verify that data was
            # in fact cached and no more than one req to mesos/marathon
            # backends were made
            ping_agent_1(ar, valid_user_header)

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')
        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        assert lbf.extra_matches == {}
        assert len(mesos_requests) == 3
        assert len(marathon_requests) == 6

    def test_if_cache_refresh_is_triggered_by_request(
            self, nginx_class, mocker, valid_user_header):
        """...right after Nginx has started."""
        filter_regexp = {
            'Executing cache refresh triggered by request': SearchCriteria(1, True),
            'Cache `[\s\w]+` empty. Fetching.': SearchCriteria(2, True),
            'Mesos state cache has been successfully updated': SearchCriteria(1, True),
            'Marathon apps cache has been successfully updated': SearchCriteria(1, True),
            }
        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')
        # Enable recording for mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        # Make sure that timers will not interfere:
        ar = nginx_class(first_poll_delay=120,
                         poll_period=120,
                         cache_expiry=115)

        with GuardedAR(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=5,
                                   line_buffer=ar.stderr_line_buffer)

            ping_agent_1(ar, valid_user_header)
            lbf.scan_log_buffer()

            # Do an extra request so that we can verify that data was in fact
            # cached and no more than one req to mesos/marathon backends were
            # made
            ping_agent_1(ar, valid_user_header)

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')
        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        assert lbf.extra_matches == {}
        assert len(mesos_requests) == 1
        assert len(marathon_requests) == 2

    def test_if_broken_marathon_does_not_break_mesos_cache(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Marathon app request failed: invalid response status: 500':
                SearchCriteria(1, True),
            'Mesos state cache has been successfully updated':
                SearchCriteria(1, True),
        }

        # Break marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='always_bork')

        ar = nginx_class()
        url = ar.make_url_from_path(
            '/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/agent-1/blah/blah')

        with GuardedAR(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            lbf.scan_log_buffer()

        assert lbf.extra_matches == {}
        assert resp.status_code == 200

    def test_if_broken_marathon_breaks_marathon_cache(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Marathon app request failed: invalid response status: 500':
                SearchCriteria(1, True),
            'Mesos state cache has been successfully updated': SearchCriteria(1, True),
            'Could not retrieve `[\s\w]+` cache entry': SearchCriteria(1, True),
        }

        # Break marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='always_bork')

        ar = nginx_class()
        url = ar.make_url_from_path('/service/foo/bar/')

        with GuardedAR(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            lbf.scan_log_buffer()

        assert resp.status_code == 503
        assert lbf.extra_matches == {}

    def test_if_broken_mesos_breaks_mesos_cache(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Mesos state request failed: invalid response status: 500':
                SearchCriteria(1, True),
            'Marathon apps cache has been successfully updated':
                SearchCriteria(1, True),
            'Coud not retrieve Mesos state cache': SearchCriteria(1, True),
        }

        # Break marathon
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='always_bork')

        ar = nginx_class()
        url = ar.make_url_from_path(
            '/agent/de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1/agent-1/blah/blah')

        with GuardedAR(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            lbf.scan_log_buffer()

        assert resp.status_code == 503
        assert lbf.extra_matches == {}

    def test_if_broken_mesos_does_not_break_marathon_cache(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Mesos state request failed: invalid response status: 500':
                SearchCriteria(1, True),
            'Marathon apps cache has been successfully updated': SearchCriteria(1, True),
        }

        # Break marathon
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='always_bork')

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='enable_nginx_task')

        ar = nginx_class()
        url = ar.make_url_from_path('/service/nginx/bar/baz')

        with GuardedAR(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            lbf.scan_log_buffer()

        assert resp.status_code == 200
        req_data = resp.json()
        assert req_data['endpoint_id'] == 'http://127.0.0.1:16001'

        assert lbf.extra_matches == {}

    def test_if_changing_marathon_apps_is_reflected_in_cache(
            self, nginx_class, valid_user_header, mocker):
        poll_period = 4
        ar = nginx_class(poll_period=poll_period, cache_expiry=3)
        url = ar.make_url_from_path('/service/nginx/bar/baz')

        with GuardedAR(ar):
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 404

            mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                func_name='enable_nginx_task')

            time.sleep(poll_period)

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200

        req_data = resp.json()
        assert req_data['endpoint_id'] == 'http://127.0.0.1:16001'

    def test_if_changing_mesos_state_is_reflected_in_cache(
            self, nginx_class, valid_user_header, mocker):
        poll_period = 4
        ar = nginx_class(poll_period=poll_period, cache_expiry=3)
        url = ar.make_url_from_path('/agent/' + EXTRA_SLAVE_DICT['id'] + '/foo/bar/')

        with GuardedAR(ar):
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 404

            mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                func_name='enable_extra_slave')

            time.sleep(poll_period)

            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200

        req_data = resp.json()
        assert req_data['endpoint_id'] == 'http://127.0.0.4:15003'

    def test_if_mesos_state_cache_works_at_all(
            self, nginx_class, mocker, valid_user_header):
        # Enable recording for mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        ar = nginx_class()

        with GuardedAR(ar):
            # Let the cache warm-up:
            time.sleep(FIRST_POLL_DELAY + 1)
            for _ in range(3):
                ping_agent_1(ar, valid_user_header)

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')

        # 3 requests + only one upstream requst == cache works
        assert len(mesos_requests) == 1

    def test_if_marathon_apps_cache_works_at_all(
            self, nginx_class, mocker, valid_user_header):
        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')
        # Enable sample Nginx task in marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='enable_nginx_task')
        # Enable recording for mesos
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')

        ar = nginx_class()
        url = ar.make_url_from_path('/service/nginx/bar/baz')

        with GuardedAR(ar):
            # Let the cache warm-up:
            time.sleep(FIRST_POLL_DELAY + 1)
            for _ in range(5):
                resp = requests.get(url,
                                    allow_redirects=False,
                                    headers=valid_user_header)
                assert resp.status_code == 200

        mesos_requests = mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                                             func_name='get_recorded_requests')
        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        # 3 requests + only one upstream requst == cache works
        assert len(mesos_requests) == 1
        assert len(marathon_requests) == 2

    def test_if_caching_works_for_marathon_leader(
            self, nginx_class, mocker, valid_user_header):
        # Enable recording for marathon
        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='record_requests')

        ar = nginx_class()
        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedAR(ar):
            # Let the cache warm-up:
            time.sleep(FIRST_POLL_DELAY + 1)
            for _ in range(5):
                resp = requests.get(url,
                                    allow_redirects=False,
                                    headers=valid_user_header)
                assert resp.status_code == 200
                req_data = resp.json()
                assert req_data['endpoint_id'] == 'http://127.0.0.2:80'

        marathon_requests = mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                                func_name='get_recorded_requests')

        # 3 requests + only one upstream requst == cache works
        assert len(marathon_requests) == 2

    def test_if_changing_marathon_leader_is_reflected_by_cache(
            self, nginx_class, mocker, valid_user_header):

        poll_period = 4
        ar = nginx_class(poll_period=poll_period, cache_expiry=3)

        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedAR(ar):
            # let's make sure that current leader is the default one
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'http://127.0.0.2:80'

            # change the leader and wait for cache to notice
            mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                                func_name='change_leader')
            time.sleep(poll_period)

            # now, let's see if the leader changed
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 200
            req_data = resp.json()
            assert req_data['endpoint_id'] == 'http://127.0.0.3:80'

    def test_if_absence_of_marathon_leader_is_handled_by_cache(
            self, nginx_class, mocker, valid_user_header):

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='remove_leader')

        ar = nginx_class()
        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedAR(ar):
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            assert resp.status_code == 404

    def test_if_broken_response_from_marathon_is_handled(
            self, nginx_class, mocker, valid_user_header):
        filter_regexp = {
            'Cannot decode Marathon leader JSON': SearchCriteria(1, True),
        }

        mocker.send_command(endpoint_id='http://127.0.0.1:8080',
                            func_name='break_leader_reply')

        ar = nginx_class()
        url = ar.make_url_from_path('/system/v1/leader/marathon/foo/bar/baz')

        with GuardedAR(ar):
            lbf = LineBufferFilter(filter_regexp,
                                   timeout=(FIRST_POLL_DELAY + 1),
                                   line_buffer=ar.stderr_line_buffer)
            resp = requests.get(url,
                                allow_redirects=False,
                                headers=valid_user_header)
            lbf.scan_log_buffer()

        assert resp.status_code == 503
        assert lbf.extra_matches == {}

# * timing out of the request ?
