# discovery: https://www.grotto-networking.com/SDNfun.html
# openflow.discovery: http://xuyansen.work/discovery-topology-in-mininet/

from pox.core import core
import pox.openflow.libopenflow_01 as of
import pox.openflow.discovery
from pox.openflow.discovery import Discovery
import pox.host_tracker
import playground.controller.toponizer
from playground.controller.toponizer import Toponizer
from pox.lib.packet.ethernet import ethernet
from pox.lib.addresses import EthAddr
import networkx as nx

log = core.getLogger()


class LoopDiscovery(object):

    def __init__(self):
        core.toponizer.addListeners(self)
        core.openflow_discovery.addListeners(self)
        core.openflow.addListeners(self)
        core.host_tracker.addListeners(self)

    # Event handlers

    def _handle_TopoUpdate(self, event):
        self.__send_flood_port_mods()
        hosts = core.toponizer.hosts()
        for (_, host_attributes) in hosts:
            macaddr = host_attributes['macaddr']
            self.__send_flow_mods_for_host(macaddr)

    def _handle_PacketIn(self, event):
        #log.debug('Handle PacketIn')
        packet = event.parsed
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        # ARP ping for unknown destination
        msg = of.ofp_packet_out()
        msg.data = event.ofp

        # Add an action to send to the specified port
        action = of.ofp_action_output(port=of.OFPP_FLOOD)
        msg.actions.append(action)

        # Send message to switch
        event.connection.send(msg)

    def _handle_ConnectionUp(self, event):
        connection = event.connection

        # Disable flood by default
        for no, port in connection.ports.iteritems():
            # Do not disable flooding to the controller
            if port.port_no >= of.OFPP_MAX:
                continue
            port_mod = self.__flood_port_mod(port, flood=False)
            connection.send(port_mod)

    # private methods

    def __send_flow_mods_for_host(self, macaddr):
        switches = core.toponizer.switches()
        for (topo_id_s, attributes_s) in switches:
            connection = core.openflow.getConnection(attributes_s['dpid'])
            host = core.toponizer.get_host_by_macaddr(macaddr)
            (topo_id_h, attributes_h) = host
            shortest_path = nx.shortest_path(core.toponizer.mst,
                                             source=topo_id_s,
                                             target=topo_id_h,
                                             weight='weight')
            gateway_topo_id = shortest_path[1]
            port_to_gateway = (core.toponizer
                                   .topo[topo_id_s]
                                        [gateway_topo_id]
                                        [0]
                                        ['port1'])
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match()
            msg.match.dl_dst = EthAddr(macaddr)
            msg.actions.append(of.ofp_action_output(port=port_to_gateway))
            connection.send(msg)

            # let the controller still handle ARP pings
            gateway_topo_id = shortest_path[1]
            port_to_gateway = (core.toponizer
                                   .topo[topo_id_s]
                                        [gateway_topo_id]
                                        [0]
                                        ['port1'])
            msg2 = of.ofp_flow_mod()
            msg2.priority += 1
            msg2.match = of.ofp_match()
            msg2.match.dl_dst = EthAddr(macaddr)
            msg2.match.dl_type = ethernet.ARP_TYPE
            msg2.actions.append(of.ofp_action_output(port=of.OFPP_CONTROLLER))
            connection.send(msg2)

    def __send_flood_port_mods(self):
        switches = core.toponizer.switches()
        for switch in switches:
            (topo_id, attributes) = switch
            for no, port in attributes['ports'].iteritems():
                if port.port_no >= of.OFPP_MAX:
                    continue
                if self.__is_flood_port(switch, port):
                    port_mod = self.__flood_port_mod(port)
                    log.debug("Enabled flooding on <s{}:p{}>"
                              .format(attributes['dpid'], port.port_no))
                else:
                    port_mod = self.__flood_port_mod(port, flood=False)
                connection = core.openflow.getConnection(attributes['dpid'])
                connection.send(port_mod)

    def __flood_port_mod(self, port, flood=True):
        port_mod = of.ofp_port_mod(port_no=port.port_no,
                                   hw_addr=port.hw_addr,
                                   config=0 if flood else of.OFPPC_NO_FLOOD,
                                   mask=of.OFPPC_NO_FLOOD)
        return port_mod

    def __is_flood_port(self, switch, port):
        (topo_id, attributes) = switch
        is_edge_port = (core.openflow_discovery
                            .is_edge_port(attributes['dpid'], port.port_no))
        is_in_spanning_tree = False

        # No need to check for edge ports
        if not is_edge_port:
            edges = core.toponizer.mst.edges(data=True)
            for (topo_id1, topo_id2, attributes) in edges:
                if topo_id == topo_id1 and port.port_no == attributes['port1']:
                    is_in_spanning_tree = True
                    break
                if topo_id == topo_id2 and port.port_no == attributes['port2']:
                    is_in_spanning_tree = True
                    break

        return is_edge_port or is_in_spanning_tree


def launch():
    def start_loop_discovery():
        core.registerNew(LoopDiscovery)

    pox.openflow.discovery.launch()
    pox.host_tracker.launch()
    playground.controller.toponizer.launch()
    core.call_when_ready(start_loop_discovery, 'toponizer')
