# -*- coding: utf-8 -*-
# Copyright (C) Mesosphere, Inc. See LICENSE file for details.

"""Mesos mock endpoint"""

import logging

from exceptions import EndpointException
from mocker.endpoints.recording import (
    RecordingHTTPRequestHandler,
    RecordingTcpIpEndpoint,
)

# pylint: disable=C0103
log = logging.getLogger(__name__)


# pylint: disable=R0903
class MesosHTTPRequestHandler(RecordingHTTPRequestHandler):
    """A request hander class mimicking Mesos master daemon.
    """
    def _calculate_response(self, base_path, *_):
        """Reply with a static Mesos state-summary response.

        Please refer to the description of the BaseHTTPRequestHandler class
        for details on the arguments and return value of this method.

        Raises:
            EndpointException: request URL path is unsupported
        """
        if base_path != '/master/state-summary':
            msg = "Path `{}` is not supported yet".format(base_path)
            blob = msg.encode('utf-8')
            raise EndpointException(code=500, reason=blob)

        res = {"cluster": "prozlach-qzpz04t",
               "frameworks": [
                   {
                       "TASK_ERROR": 0,
                       "TASK_FAILED": 0,
                       "TASK_FINISHED": 0,
                       "TASK_KILLED": 0,
                       "TASK_KILLING": 0,
                       "TASK_LOST": 0,
                       "TASK_RUNNING": 0,
                       "TASK_STAGING": 0,
                       "TASK_STARTING": 0,
                       "active": True,
                       "capabilities": [],
                       "hostname": "10.0.5.35",
                       "id": "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-0001",
                       "name": "metronome",
                       "offered_resources": {
                           "cpus": 0.0,
                           "disk": 0.0,
                           "gpus": 0.0,
                           "mem": 0.0
                       },
                       "pid": "scheduler-f43b84ec-16c3-455c-94df-158885642b88@10.0.5.35:36857",
                       "slave_ids": [],
                       "used_resources": {
                           "cpus": 0.0,
                           "disk": 0.0,
                           "gpus": 0.0,
                           "mem": 0.0
                       },
                       "webui_url": "http://10.0.5.35:9090"
                   },
                   {
                       "TASK_ERROR": 0,
                       "TASK_FAILED": 0,
                       "TASK_FINISHED": 0,
                       "TASK_KILLED": 0,
                       "TASK_KILLING": 0,
                       "TASK_LOST": 0,
                       "TASK_RUNNING": 0,
                       "TASK_STAGING": 0,
                       "TASK_STARTING": 0,
                       "active": True,
                       "capabilities": [
                           "TASK_KILLING_STATE",
                           "PARTITION_AWARE"
                       ],
                       "hostname": "10.0.5.35",
                       "id": "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-0000",
                       "name": "marathon",
                       "offered_resources": {
                           "cpus": 0.0,
                           "disk": 0.0,
                           "gpus": 0.0,
                           "mem": 0.0
                       },
                       "pid": "scheduler-43d78acd-8c22-4a42-82e5-43c64407038c@10.0.5.35:38457",
                       "slave_ids": [],
                       "used_resources": {
                           "cpus": 0.0,
                           "disk": 0.0,
                           "gpus": 0.0,
                           "mem": 0.0
                       },
                       "webui_url": "https://10.0.5.35:8443"
                   }
               ],
               "hostname": "10.0.5.35",
               "slaves": [
                   {
                       "TASK_ERROR": 0,
                       "TASK_FAILED": 0,
                       "TASK_FINISHED": 0,
                       "TASK_KILLED": 0,
                       "TASK_KILLING": 0,
                       "TASK_LOST": 0,
                       "TASK_RUNNING": 0,
                       "TASK_STAGING": 0,
                       "TASK_STARTING": 0,
                       "active": True,
                       "attributes": {},
                       "framework_ids": [],
                       "hostname": "10.0.1.10",
                       "id": "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S1",
                       "offered_resources": {
                           "cpus": 0.0,
                           "disk": 0.0,
                           "gpus": 0.0,
                           "mem": 0.0
                       },
                       "pid": "slave(1)@10.0.1.10:5051",
                       "registered_time": 1480619701.48294,
                       "reserved_resources": {},
                       "resources": {
                           "cpus": 4.0,
                           "disk": 35577.0,
                           "gpus": 0.0,
                           "mem": 14018.0,
                           "ports": ("[1025-2180, 2182-3887, 3889-5049,"
                                     "5052-8079, 8082-8180, 8182-32000]")
                       },
                       "unreserved_resources": {
                           "cpus": 4.0,
                           "disk": 35577.0,
                           "gpus": 0.0,
                           "mem": 14018.0,
                           "ports": ("[1025-2180, 2182-3887, 3889-5049,"
                                     "5052-8079, 8082-8180, 8182-32000]")
                       },
                       "used_resources": {
                           "cpus": 0.0,
                           "disk": 0.0,
                           "gpus": 0.0,
                           "mem": 0.0
                       },
                       "version": "1.2.0"
                   },
                   {
                       "TASK_ERROR": 0,
                       "TASK_FAILED": 0,
                       "TASK_FINISHED": 0,
                       "TASK_KILLED": 0,
                       "TASK_KILLING": 0,
                       "TASK_LOST": 0,
                       "TASK_RUNNING": 0,
                       "TASK_STAGING": 0,
                       "TASK_STARTING": 0,
                       "active": True,
                       "attributes": {
                           "public_ip": "true"
                       },
                       "framework_ids": [],
                       "hostname": "10.0.4.214",
                       "id": "de1baf83-c36c-4d23-9cb0-f89f596cd6ab-S0",
                       "offered_resources": {
                           "cpus": 0.0,
                           "disk": 0.0,
                           "gpus": 0.0,
                           "mem": 0.0
                       },
                       "pid": "slave(1)@10.0.4.214:5051",
                       "registered_time": 1480619699.20796,
                       "reserved_resources": {
                           "slave_public": {
                               "cpus": 4.0,
                               "disk": 35577.0,
                               "gpus": 0.0,
                               "mem": 14018.0,
                               "ports": "[1-21, 23-5050, 5052-32000]"
                           }
                       },
                       "resources": {
                           "cpus": 4.0,
                           "disk": 35577.0,
                           "gpus": 0.0,
                           "mem": 14018.0,
                           "ports": "[1-21, 23-5050, 5052-32000]"
                       },
                       "unreserved_resources": {
                           "cpus": 0.0,
                           "disk": 0.0,
                           "gpus": 0.0,
                           "mem": 0.0
                       },
                       "used_resources": {
                           "cpus": 0.0,
                           "disk": 0.0,
                           "gpus": 0.0,
                           "mem": 0.0
                       },
                       "version": "1.2.0"
                   }
                   ]
               }

        blob = self._convert_data_to_blob(res)

        return blob


# pylint: disable=R0903,C0103
class MesosEndpoint(RecordingTcpIpEndpoint):
    """An endpoint that mimics DC/OS leader.mesos Mesos"""
    def __init__(self, port, ip=''):
        super().__init__(port, ip, MesosHTTPRequestHandler)
