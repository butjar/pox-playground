#!/usr/bin/python

from mininet.topolib import TreeTopo
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Controller
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel

import os

CURRENT_DIR = os.path.dirname(os.path.realpath('__file__'))

# http://mininet.org/blog/2013/06/03/automating-controller-startup/
class LoopController(Controller):
    def __init__(self,
                 name,
                 cdir=CURRENT_DIR,
                 command='./pox-wrapper.py',
                 cargs=('controller.loop_discovery --port=%s --file=pox.log'),
                 **kwargs):
        Controller.__init__(self,
                            name,
                            cdir=cdir,
                            command=command,
                            cargs=cargs,
                            **kwargs)

controllers = { 'loop_controller': LoopController }


def create_network(net=Mininet(controller=LoopController)):
    # Add hosts
    h1 = net.addHost('h1')
    h2 = net.addHost('h2')
    h3 = net.addHost('h3')

    #Add controller
    #c1 = net.addController('c1', controller=LoopController)
    c1 = net.addController('c1', controller=RemoteController)

    # Add switches
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')
    s3 = net.addSwitch('s3')

    # Add links
    net.addLink(s1, s2)
    net.addLink(s1, s3)
    net.addLink(s2, s3)
    net.addLink(h1, s1)
    net.addLink(h1, s2)
    net.addLink(h2, s2)
    net.addLink(h3, s3)

    return net


def provision_nodes(net):
    pass
    #print net.get('h1').cmd("ping h2")

if __name__ == '__main__':
    setLogLevel('info')
    net = create_network()
    net.start()
    provision_nodes(net)
    CLI(net)
    net.stop()
