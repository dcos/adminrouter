# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""
Programmable in-memory DNS server
"""

import copy
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


DEFAULT_TTL = 60

# Records that MesosDNSResolver uses to construct replies. We're not adding
# rname at this place as it can be overriden by MesosDNSResolver TLD
# configuration. The each record's key is used as a DNS label that is put
# before TLD in the final answer, i.e.: "master" -> "master.mesos."
MESOS_DNS_RECORDS = {
    "leader": RR(
        rtype=QTYPE.A,
        rclass=1,
        ttl=DEFAULT_TTL,
        rdata=A("127.0.0.2")),
    "master": RR(
        rtype=QTYPE.A,
        rclass=1,
        ttl=DEFAULT_TTL,
        rdata=A('127.0.0.1')),
    "agent": RR(
        rtype=QTYPE.A,
        rclass=1,
        ttl=DEFAULT_TTL,
        rdata=A('127.0.0.1')),
    "slave": RR(
        rtype=QTYPE.A,
        rclass=1,
        ttl=DEFAULT_TTL,
        rdata=A('127.0.0.1')),
}


class MesosDNSResolver(BaseResolver):
    """MesosDNSResolver returns responses to *.mesos queries

    By default it reads supported responses from `MESOS_DNS_RECORDS` and it
    allows to override paramters of all responses TTLs and also leader IP
    address.

    Args:
        leader_ip: Override the IP address of leader.mesos query
        ttl: Override the TTL of all replies
        domain: Override the TLD (defaults to mesos.)
    """

    def __init__(self, leader_ip=None, ttl=None, domain=DomainName('mesos')):
        self.leader_ip = leader_ip
        self.ttl = ttl
        self.domain = domain

    def resolve(self, request, handler):

        for name, rr in MESOS_DNS_RECORDS.items():
            # DNS resolver allows to override TLD domain so  we construct FQDN
            # that can be compared with request
            fqdn = "{}.{}.".format(name, self.domain)
            # For now we're comparing only the name and rtype
            if str(request.q.qname) == fqdn and request.q.qtype == rr.rtype:
                reply = request.reply()

                answer = copy.deepcopy(rr)
                answer.rname = fqdn

                # This server allows to override TTL and leader_ip
                if self.ttl:
                    answer.ttl = self.ttl

                if name == "leader" and self.leader_ip:
                    answer.rdata = A(self.leader_ip)

                reply.add_answer(answer)
                return reply

        log.debug((
            "MesosLeaderResolver: not a support *.mesos DNS query "
            "returning empty reponse"))
        return EmptyResolver().resolve(request, handler)


class MesosDNSServer:
    """Simple DNS server that responds to *.mesos DNS queries"""

    def __init__(self, server_address, leader_ip):
        self._default_resolver = MesosDNSResolver(leader_ip)
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
        self._server.server.resolver = MesosDNSResolver(leader_ip, ttl=ttl)
