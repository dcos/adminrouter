# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

import time
import pytest

from util import GuardedSubprocess

from generic_test_code import (
    generic_correct_upstream_dest_test,
    ping_mesos_agent,
)


class TestNginxResolver:

    # For testing purposes we'll use short DNS records TTL
    SHORT_TTL = 1

    @pytest.mark.parametrize("path,dest_port",
                             [("/system/v1/leader/mesos/foo/bar", 80),
                              ("/mesos/master/state-summary", 5050),
                              ])
    def test_mesos_leader_reresolve_in_proxy_pass(
            self,
            nginx_class,
            superuser_user_header,
            dns_server_mock,
            path,
            dest_port,
            ):
        # Respond with default leader instance and TTL=1s
        dns_server_mock.reply_with_leader_ip('127.0.0.10', ttl=self.SHORT_TTL)

        ar = nginx_class()
        with GuardedSubprocess(ar):
            generic_correct_upstream_dest_test(
                ar,
                superuser_user_header,
                path,
                "http://127.0.0.10:{}".format(dest_port),
                )

            dns_server_mock.reply_with_leader_ip('127.0.0.11', ttl=self.SHORT_TTL)
            # The MesosLeaderDNSServer resolves leader.mesos with TTL=1s so
            # its enough to wait for 2 seconds here
            time.sleep(self.SHORT_TTL * 2)

            generic_correct_upstream_dest_test(
                ar,
                superuser_user_header,
                path,
                "http://127.0.0.11:{}".format(dest_port),
                )

    def test_if_mesos_leader_is_reresolved_by_lua(
            self, nginx_class, mocker, dns_server_mock, superuser_user_header):
        # Respond with default leader instance and TTL=1s
        dns_server_mock.reply_with_leader_ip('127.0.0.2', ttl=self.SHORT_TTL)

        cache_poll_period = 3

        # Enable recording for both mesos instances
        mocker.send_command(
            endpoint_id='http://127.0.0.2:5050',
            func_name='record_requests',
            )
        mocker.send_command(
            endpoint_id='http://127.0.0.3:5050',
            func_name='record_requests',
            )

        ar = nginx_class(
            upstream_mesos="http://leader.mesos:5050",
            cache_poll_period=cache_poll_period,
            cache_expiration=(cache_poll_period - 1),
            )

        with GuardedSubprocess(ar):
            ping_mesos_agent(ar, superuser_user_header)

            dns_server_mock.reply_with_leader_ip('127.0.0.3', ttl=self.SHORT_TTL)
            # Wait for cache to expire and let it be re-resolved
            time.sleep(cache_poll_period * 2)

            ping_mesos_agent(ar, superuser_user_header)

        leader_1_requests = mocker.send_command(
            endpoint_id='http://127.0.0.2:5050',
            func_name='get_recorded_requests',
            )
        leader_2_requests = mocker.send_command(
            endpoint_id='http://127.0.0.3:5050',
            func_name='get_recorded_requests',
            )

        # Check that both mesos masters were queried once for it's state-summary
        # which means that after failing original leader new leader was resolved
        # by lua http library
        assert len(leader_1_requests) == 1
        assert len(leader_2_requests) == 1
