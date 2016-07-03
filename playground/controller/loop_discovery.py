# discovery: https://www.grotto-networking.com/SDNfun.html
# openflow.discovery: http://xuyansen.work/discovery-topology-in-mininet/

import uuid
from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.packet.ethernet import ethernet
from pox.lib.addresses import EthAddr
import pox.openflow.discovery
from pox.openflow.discovery import Discovery
import networkx as nx
import pox.host_tracker

log = core.getLogger()


class LoopDiscovery(object):

    @staticmethod
    def assign_node_id():
        return str(uuid.uuid1())

    def __init__(self):
        self.topo = nx.MultiDiGraph()
        self.mst = None
        core.openflow_discovery.addListeners(self)
        core.openflow.addListeners(self)
        core.host_tracker.addListeners(self)

    # Event handlers

    def _handle_PacketIn(self, event):
        log.debug('Recieved packet in')
        packet = event.parsed
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        # ARP ping for unknown destination
        known_macs = map(lambda (_, attr): attr['macaddr'], self.__hosts())
        if not (packet.src in known_macs):
            log.debug("unknown src")

        msg = of.ofp_packet_out()
        msg.data = event.ofp

        # Add an action to send to the specified port
        action = of.ofp_action_output(port=of.OFPP_FLOOD)
        msg.actions.append(action)

        # Send message to switch
        event.connection.send(msg)

    def _handle_ConnectionUp(self, event):
        connection = event.connection
        log.debug("Adding Switch <{}> to topology".format(connection.dpid))
        self.__add_switch(connection)

        # Disable flood by default
        for no, port in connection.ports.iteritems():
            # Do not disable flooding to the controller
            if port.port_no >= of.OFPP_MAX:
                continue
            port_mod = self.__flood_port_mod(port, flood=False)
            connection.send(port_mod)

    def _handle_LinkEvent(self, event):
        if(event.added):
            link = event.link
            log.debug("Adding link between <s{}:p{}> and <s{}:p{}> to topology"
                      .format(link.dpid1,
                              link.port1,
                              link.dpid2,
                              link.port2))
            self.__add_switch_to_switch_connection(link.dpid1,
                                                   link.dpid2,
                                                   link.port1,
                                                   link.port2)
        elif(event.removed):
            pass
        else:
            log.error('Unknown event on LinkEvent: {}'.format(event))

        log.debug('Updating minimal spanning tree '
                  'and pushing flow and port mods')
        self.mst = self.__minimal_spanning_tree()
        self.__send_flood_port_mods()

    def _handle_HostEvent(self, event):
        if event.join:
            # I know, I'm  looping over the same array twice ...
            entry = event.entry
            if not self.__get_host_by_macaddr(entry.macaddr):
                log.debug("Adding host <{}> to topology".format(entry.macaddr))
                self.__add_host(entry)
            if not self.__is_host_connected_to_switch(entry.macaddr,
                                                      entry.dpid):
                log.debug('Adding links between host <{}>'
                          'and switch <s{}:p{}> to topology'
                          .format(entry.macaddr, entry.dpid, entry.port))
                self.__add_switch_to_host_connection(entry.dpid,
                                                     entry.port,
                                                     entry.macaddr)
            log.debug('Updating minimal spanning tree'
                      'and pushing flow and port mods')
            self.mst = self.__minimal_spanning_tree()
            self.__send_flow_mods_for_host(entry.macaddr)

    # private methods

    def __add_host(self, entry):
        self.topo.add_node(LoopDiscovery.assign_node_id(),
                           type='host',
                           macaddr=entry.macaddr)

    def __add_switch(self, connection, graph=None):
        graph = graph if graph else self.topo
        graph.add_node(LoopDiscovery.assign_node_id(),
                       type='switch',
                       ports=connection.ports,
                       dpid=connection.dpid,
                       features=connection.features)

    def __add_switch_to_host_connection(self,
                                        dpid,
                                        port,
                                        macaddr,
                                        weight=1,
                                        graph=None):
        (topo_id_s, _) = self.__get_switch_by_dpid(dpid)
        (topo_id_h, _) = self.__get_host_by_macaddr(macaddr)
        graph = graph if graph else self.topo
        graph.add_edge(topo_id_s,
                       topo_id_h,
                       port1=port,
                       port2=None,
                       weight=weight)
        graph.add_edge(topo_id_h,
                       topo_id_s,
                       port1=None,
                       port2=port,
                       weight=weight)

    def __add_switch_to_switch_connection(self,
                                          dpid1,
                                          dpid2,
                                          port1,
                                          port2,
                                          weight=1,
                                          graph=None):
        (topo_id_s1, _) = self.__get_switch_by_dpid(dpid1)
        (topo_id_s2, _) = self.__get_switch_by_dpid(dpid2)
        graph = graph if graph else self.topo
        graph.add_edge(topo_id_s1,
                       topo_id_s2,
                       port1=port1,
                       port2=port2,
                       weight=weight)

    def __filter_by_attribute(self,
                              attribute,
                              value,
                              filter_list=None):
        filter_list = (filter_list if filter_list
                       else self.topo.nodes(data=True))
        return filter(lambda (x, y): y[attribute] == value, filter_list)

    def __first_node_by_attribute(self, attribute, value, nodes=None):
        nodes = nodes if nodes else self.topo.nodes(data=True)
        try:
            node = next((n, attr)
                        for (n, attr) in nodes
                        if attribute in attr and attr[attribute] == value)
        except StopIteration as e:
            node = None
        return node

    def __flood_port_mod(self, port, flood=True):
        port_mod = of.ofp_port_mod(port_no=port.port_no,
                                   hw_addr=port.hw_addr,
                                   config=0 if flood else of.OFPPC_NO_FLOOD,
                                   mask=of.OFPPC_NO_FLOOD)
        return port_mod

    def __get_host_by_macaddr(self, macaddr):
        hosts = self.__hosts()
        return self.__first_node_by_attribute('macaddr', macaddr, hosts)

    def __get_switch_by_dpid(self, dpid):
        return self.__first_node_by_attribute('dpid', dpid, self.__switches())

    def __hosts(self, graph=None):
        graph = graph if graph else self.topo.nodes(data=True)
        return self.__filter_by_attribute('type', 'host', filter_list=graph)

    def __is_flood_port(self, switch, port):
        (topo_id, attributes) = switch
        is_edge_port = (core.openflow_discovery
                            .is_edge_port(attributes['dpid'], port.port_no))
        is_in_spanning_tree = False

        # No need to check for edge ports
        if not is_edge_port:
            for (topo_id1, topo_id2, attributes) in self.mst.edges(data=True):
                if topo_id == topo_id1 and port.port_no == attributes['port1']:
                    is_in_spanning_tree = True
                    break
                if topo_id == topo_id2 and port.port_no == attributes['port2']:
                    is_in_spanning_tree = True
                    break

        return is_edge_port or is_in_spanning_tree

    def __is_host_connected_to_switch(self, macaddr, dpid, graph=None):
        graph = graph if graph else self.topo
        (topo_id_h, _) = self.__get_host_by_macaddr(macaddr)
        (topo_id_s, _) = self.__get_switch_by_dpid(dpid)
        return graph.has_edge(topo_id_h, topo_id_s)

    def __links(self, graph=None):
        graph = graph if graph else self.topo
        links = graph.edges(data=True)
        return links

    def __minimal_spanning_tree(self):
        undirected_graph = self.topo.to_undirected(reciprocal=True)
        # Unfortunatly the theMultiDiGraph.to_undirected selects arbitrary
        # attributes for the edge. Needs to be corrected manually.
        # http://networkx.readthedocs.io/en/stable/_modules/networkx/classes/multidigraph.html#MultiDiGraph.to_undirected
        for (topo_id1, topo_id2) in undirected_graph.edges():
            links = self.topo[topo_id1][topo_id2]
            attributes = undirected_graph[topo_id1][topo_id2][0]
            if 'port1' in attributes:
                attributes['port1'] = links[0]['port1']
            if 'port2' in attributes:
                attributes['port2'] = links[0]['port2']
        return nx.minimum_spanning_tree(undirected_graph)

    def __send_flow_mods_for_host(self, macaddr):
        switches = self.__switches()
        for (topo_id_s, attributes_s) in switches:
            connection = core.openflow.getConnection(attributes_s['dpid'])
            (topo_id_h, attributes_h) = self.__get_host_by_macaddr(macaddr)
            shortest_path = nx.shortest_path(self.mst,
                                             source=topo_id_s,
                                             target=topo_id_h,
                                             weight='weight')
            gateway_topo_id = shortest_path[1]
            port_to_gateway = self.topo[topo_id_s][gateway_topo_id][0]['port1']
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match()
            msg.match.dl_dst = EthAddr(macaddr)
            msg.actions.append(of.ofp_action_output(port=port_to_gateway))
            connection.send(msg)

            # let the controller still handle ARP pings
            gateway_topo_id = shortest_path[1]
            port_to_gateway = self.topo[topo_id_s][gateway_topo_id][0]['port1']
            msg2 = of.ofp_flow_mod()
            msg2.priority += 1
            msg2.match = of.ofp_match()
            msg2.match.dl_dst = EthAddr(macaddr)
            msg2.match.dl_type = ethernet.ARP_TYPE
            msg2.actions.append(of.ofp_action_output(port=of.OFPP_CONTROLLER))
            connection.send(msg2)

    def __send_flood_port_mods(self):
        for switch in self.__switches():
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

    def __switches(self, graph=None):
        graph = graph if graph else self.topo.nodes(data=True)
        return self.__filter_by_attribute('type', 'switch', filter_list=graph)


def launch():
    pox.openflow.discovery.launch()
    pox.host_tracker.launch()
    core.registerNew(LoopDiscovery)
