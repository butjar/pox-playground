# Copyright 2015 Greg M. Bernstein
# Initially based on the POX l2_learning.py file by James McCauley
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This POX application demonstrates destination based L2 forwarding SDN Network
for a static (given) network. The default forwarding is shortest paths (like
IEEE SPB or TRILL), but you can set an option to enable widest path forwarding.
The name of the file describing the network is specified via the pox command
line after this file. The exact same network description should be furnished to
Mininet.
Note that I assume the switch names start with "S", but this can be easily changed.

One needs to set the Python path variables so python/pox can find this module
and its dependencies. From the directory where this file exists I use the
following (MS Windows):
set PYTHONPATH=.;
python \python-tools\pox\pox.py l2DestForwardStatic --netfile=ExNetwithLoops1A.js

or if you want to use the widest paths

python \python-tools\pox\pox.py l2DestForwardStatic --netfile=ExNetwithLoops1A.js --widest_paths=True
"""

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import EthAddr

import json
from networkx.readwrite import json_graph
import ShortestPathBridge as spb
import WidestPathBridge as wpb

log = core.getLogger()


class L2DestForwardStatic(object):
    """
    Waits for OpenFlow switches to connect and then fills their forwarding tables based on
    given network topology.
    """
    def __init__(self, netfile, widest_paths):
        """
        Compute the forwarding tables based on the network description file,
        and whether shortest or widest paths should be used.
        """
        print "Computing forwarding table for: {}".format(netfile)
        self.g = json_graph.node_link_graph(json.load(open(netfile)))
        if widest_paths:
            self.fwdTable = wpb.computeL2FwdTables(self.g)
        else:
            self.fwdTable = spb.computeL2FwdTables(self.g)
        core.openflow.addListeners(self)

    def _handle_ConnectionUp(self, event):
        """ This method gets called when a switch connects to the controller.
            We fill in the forwarding tables for the switch here.
        """
        connection = event.connection
        print "Switch {} came up".format(connection.dpid)
        print "Port information {}".format(connection.ports)
        log.debug("Connection %s" % (event.connection,))
        self.load_fwd_table(connection)

    def load_fwd_table(self, connection):
        """ This method does the nitty gritty of creating and sending the
            OpenFlow messages based on the pre-computed forwarding tables."""
        dpid = connection.dpid
        sname = "S" + str(dpid)
        print "setting up forwarding table for switch {}".format(sname)
        table = self.fwdTable[sname]
        for mac in table.keys():
            dstMAC = EthAddr(mac)
            print "Mac address string {} and number {}".format(mac, dstMAC)
            msg = of.ofp_flow_mod()
            of_match = of.ofp_match(dl_dst=dstMAC)
            of_action = of.ofp_action_output(port=table[mac])
            msg.match = of_match
            msg.actions.append(of_action)
            connection.send(msg)


def launch(netfile, widest_paths=False):
    """
    Starts a L2 Destination Based Forwarding application in POX. The netfile must be specified on
    the command line.
    """
    core.registerNew(L2DestForwardStatic, netfile, widest_paths)
