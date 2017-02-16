# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import requests
import time

from runner.common import CACHE_FIRST_POLL_DELAY
from util import GuardedSubprocess

from generic_test_code import (
    generic_correct_upstream_dest_test,
    ping_mesos_agent,
)


class TestNginxResolver:

    # For testing purposes we'll use short DNS records TTL
    SHORT_TTL = 1

    def test_if_mesos_leader_is_reresolved_in_proxy_pass(
            self, nginx_class, valid_user_header, dns_server_mock):
        # Respond with default leader instance and TTL=1s
        dns_server_mock.reply_with_leader_ip('127.0.0.2', ttl=self.SHORT_TTL)

        ar = nginx_class()
        with GuardedSubprocess(ar):
            # Mesos prefixed URL should be forwarded to Mesos leader instance
            url = ar.make_url_from_path('/mesos/master/state-summary')

            # Make sure that request was proxied to MesosEndpoint mock which
            # returns data that looks like actual cluster state summary
            r = requests.get(
                url, allow_redirects=True, headers=valid_user_header)
            assert r.status_code == 200
            assert r.json()["cluster"] == "prozlach-qzpz04t"

            dns_server_mock.reply_with_leader_ip('127.0.0.5', ttl=self.SHORT_TTL)
            # The MesosLeaderDNSServer resolves leader.mesos with TTL=1s so
            # its enough to wait for 2 seconds here
            time.sleep(self.SHORT_TTL * 2)

            # Make sure that second request was forwarded to new leader
            # which is an instance of ReflectingTcpIpEndpoint
            r = requests.get(
                url, allow_redirects=True, headers=valid_user_header)
            assert r.status_code == 200
            assert r.json()["endpoint_id"] == "http://127.0.0.5:5050"

    def test_if_mesos_leader_ar_instance_is_reresolved_in_proxy_pass(
            self, nginx_class, dns_server_mock, superuser_user_header):
        # Respond with default leader instance and TTL=1s
        dns_server_mock.reply_with_leader_ip('127.0.0.2', ttl=self.SHORT_TTL)

        ar = nginx_class()
        with GuardedSubprocess(ar):
            generic_correct_upstream_dest_test(
                ar,
                superuser_user_header,
                '/system/v1/leader/mesos/foo/bar',
                'http://127.0.0.2:80',
                )

            dns_server_mock.reply_with_leader_ip('127.0.0.5', ttl=self.SHORT_TTL)
            # The MesosLeaderDNSServer resolves leader.mesos with TTL=1s so
            # its enough to wait for 2 seconds here
            time.sleep(self.SHORT_TTL * 2)

            # Leader has changed so new instance should be forwarded to AR
            # instance that runs on different leader
            generic_correct_upstream_dest_test(
                ar,
                superuser_user_header,
                '/system/v1/leader/mesos/foo/bar',
                'http://127.0.0.5:80',
                )

    def test_if_mesos_leader_is_reresolved_by_lua(
            self, nginx_class, mocker, dns_server_mock, superuser_user_header):
        # Respond with default leader instance and TTL=1s
        dns_server_mock.reply_with_leader_ip('127.0.0.2', ttl=self.SHORT_TTL)

        cache_poll_period = 3

        # Enable recording for both mesos instances
        mocker.send_command(endpoint_id='http://127.0.0.2:5050',
                            func_name='record_requests')
        mocker.send_command(endpoint_id='http://127.0.0.6:5050',
                            func_name='record_requests')

        ar = nginx_class(
            cache_poll_period=cache_poll_period,
            cache_expiration=(cache_poll_period - 1)
            )

        with GuardedSubprocess(ar):
            # Let the cache warm-up:
            time.sleep(CACHE_FIRST_POLL_DELAY + 1)
            for _ in range(3):
                ping_mesos_agent(ar, superuser_user_header)

            dns_server_mock.reply_with_leader_ip('127.0.0.6', ttl=self.SHORT_TTL)
            # Wait for cache to expire and let it be re-resolved
            time.sleep(cache_poll_period + 1)

            for _ in range(3):
                ping_mesos_agent(ar, superuser_user_header)

        leader_1_requests = mocker.send_command(
            endpoint_id='http://127.0.0.2:5050',
            func_name='get_recorded_requests',
            )
        leader_2_requests = mocker.send_command(
            endpoint_id='http://127.0.0.6:5050',
            func_name='get_recorded_requests',
            )

        # Check that both mesos masters were queried once for it's state-summary
        # which means that after failing original leader new leader was resolved
        # by lua http library
        assert len(leader_1_requests) == 1
        assert len(leader_2_requests) == 1
