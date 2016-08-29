import uuid
from pox.core import core
from pox.lib.revent import *
import pox.openflow.discovery
from pox.openflow.discovery import Discovery
import pox.host_tracker
from pox.lib.packet.ethernet import ethernet
from pox.lib.addresses import EthAddr
import networkx as nx

log = core.getLogger()


class TopoUpdate (Event):
  """
  Topology events
  """
  def __init__ (self, mst, topo):
    Event.__init__(self)
    self.mst = mst
    self.topo = topo

class Toponizer(EventMixin):

    _core_name = 'toponizer'
    _eventMixin_events = set([
        TopoUpdate,
    ])

    @staticmethod
    def assign_node_id():
        return str(uuid.uuid1())

    def __init__(self):
        self.topo = nx.MultiDiGraph()
        self.mst = None
        core.openflow_discovery.addListeners(self)
        core.openflow.addListeners(self)
        core.host_tracker.addListeners(self)

    def add_host(self, entry):
        self.topo.add_node(Toponizer.assign_node_id(),
                           type='host',
                           macaddr=entry.macaddr)

    def add_switch(self, connection, graph=None):
        graph = graph if graph else self.topo
        graph.add_node(Toponizer.assign_node_id(),
                       type='switch',
                       ports=connection.ports,
                       dpid=connection.dpid,
                       features=connection.features)

    def switches(self, graph=None):
        graph = graph if graph else self.topo.nodes(data=True)
        return self.__filter_by_attribute('type', 'switch', filter_list=graph)

    def hosts(self, graph=None):
        graph = graph if graph else self.topo.nodes(data=True)
        return self.__filter_by_attribute('type', 'host', filter_list=graph)

    def links(self, graph=None):
        graph = graph if graph else self.topo
        links = graph.edges(data=True)
        return links

    def get_host_by_macaddr(self, macaddr):
        hosts = self.hosts()
        return self.__first_node_by_attribute('macaddr', macaddr, hosts)

    def get_switch_by_dpid(self, dpid):
        return self.__first_node_by_attribute('dpid', dpid, self.switches())

    # event handlers

    def _handle_ConnectionUp(self, event):
        connection = event.connection
        log.debug("Adding Switch <{}> to topology".format(connection.dpid))
        self.add_switch(connection)

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
            link = event.link
            log.debug('Removing link between <s{}:p{}>'
                      'and <s{}:p{}> from topology'
                      .format(link.dpid1,
                              link.port1,
                              link.dpid2,
                              link.port2))
            self.__remove_switch_to_switch_connection(link.dpid1,
                                                      link.dpid2,
                                                      link.port1,
                                                      link.port2)
        else:
            log.error('Unknown event on LinkEvent: {}'.format(event))

        log.debug('Updating minimal spanning tree')
        self.mst = self.__minimal_spanning_tree()
        self.raiseEventNoErrors(TopoUpdate, self.mst, self.topo)

    def _handle_HostEvent(self, event):
        if event.join:
            # I know, I'm  looping over the same array twice ...
            entry = event.entry
            if not self.get_host_by_macaddr(entry.macaddr):
                log.debug("Adding host <{}> to topology".format(entry.macaddr))
                self.add_host(entry)
            if not self.__is_host_connected_to_switch(entry.macaddr,
                                                      entry.dpid):
                log.debug('Adding links between host <{}>'
                          'and switch <s{}:p{}> to topology'
                          .format(entry.macaddr, entry.dpid, entry.port))
                self.__add_switch_to_host_connection(entry.dpid,
                                                     entry.port,
                                                     entry.macaddr)
        log.debug('Updating minimal spanning tree')
        self.mst = self.__minimal_spanning_tree()
        self.raiseEventNoErrors(TopoUpdate, self.mst, self.topo)

    # private methods

    def __add_switch_to_host_connection(self,
                                        dpid,
                                        port,
                                        macaddr,
                                        weight=1,
                                        graph=None):
        (topo_id_s, _) = self.get_switch_by_dpid(dpid)
        (topo_id_h, _) = self.get_host_by_macaddr(macaddr)
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
        (topo_id_s1, _) = self.get_switch_by_dpid(dpid1)
        (topo_id_s2, _) = self.get_switch_by_dpid(dpid2)
        graph = graph if graph else self.topo
        graph.add_edge(topo_id_s1,
                       topo_id_s2,
                       port1=port1,
                       port2=port2,
                       weight=weight)

    def __remove_switch_to_switch_connection(self,
                                             dpid1,
                                             dpid2,
                                             port1,
                                             port2,
                                             weight=1,
                                             graph=None):
        (topo_id_s1, _) = self.get_switch_by_dpid(dpid1)
        (topo_id_s2, _) = self.get_switch_by_dpid(dpid2)
        graph = graph if graph else self.topo
        graph.remove_edge(topo_id_s1,
                          topo_id_s2)
        self.raiseEventNoErrors(TopoUpdate, self.mst, self.topo)


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

    def __is_host_connected_to_switch(self, macaddr, dpid, graph=None):
        graph = graph if graph else self.topo
        (topo_id_h, _) = self.get_host_by_macaddr(macaddr)
        (topo_id_s, _) = self.get_switch_by_dpid(dpid)
        return graph.has_edge(topo_id_h, topo_id_s)

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


def launch():
    core.registerNew(Toponizer)
