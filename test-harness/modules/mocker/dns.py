# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""
Programmable in-memory DNS server
"""

import logging

from dnslib import (
    A,
    QTYPE,
    RR,
)

from dnslib.server import (
    BaseResolver,
    DNSLogger,
    DNSServer,
)

log = logging.getLogger(__name__)


class DomainName(str):
    """DomainName is helper class that allow easier manipulation with DNS names.

       Example:
          com = DomainName("com")
          assert com.example == "example.com"
    """

    def __getattr__(self, item):
        return DomainName(item + '.' + self)


class EmptyResolver(BaseResolver):
    """EmptyResolver returns empty reply for any DNS query"""

    def resolve(self, request, handler):
        return request.reply()


class MesosLeaderResolver(BaseResolver):
    """MesosLeaderResolver returns responses to leader.mesos queries"""

    DEFAULT_TTL = 60

    def __init__(self, leader_ip, ttl=None, domain=DomainName('mesos')):
        if ttl is None:
            ttl = self.DEFAULT_TTL

        self.leader_ip = leader_ip
        self.ttl = ttl
        self.domain = domain

    def resolve(self, request, handler):
        # We can respond only to leader.mesos A requests
        if (str(request.q.qname) == (self.domain.leader + ".") and
                QTYPE[request.q.qtype] == "A"):

            reply = request.reply()
            reply.add_answer(RR(
                rname=self.domain.leader,
                rtype=QTYPE.A,
                rclass=1,
                ttl=self.ttl,
                rdata=A(self.leader_ip)))
            return reply

        log.debug((
            "MesosLeaderResolver: not a leader.mesos DNS query "
            "returning empty reponse"))
        return EmptyResolver().resolve(request, handler)


class MesosLeaderDNSServer:
    """Simple DNS server that responds to leader.mesos DNS queries"""

    def __init__(self, server_address, leader_ip):
        self._default_resolver = MesosLeaderResolver(leader_ip)
        self._server = DNSServer(
            resolver=self._default_resolver,
            address=server_address[0],
            port=server_address[1],
            logger=DNSLogger("pass"),  # Don't log anything to stdout
            )

    def start(self):
        self._server.start_thread()

    def stop(self):
        self._server.stop()

    def reset(self):
        self._server.server.resolver = self._default_resolver

    def reply_with_leader_ip(self, leader_ip, ttl=None):
        """Changes the IP of resolved leader.mesos queries"""
        self._server.server.resolver = MesosLeaderResolver(leader_ip, ttl=ttl)
