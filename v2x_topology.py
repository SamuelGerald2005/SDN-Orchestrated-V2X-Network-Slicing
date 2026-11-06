#!/usr/bin/env python3
"""
V2X SDN Topology
2 RSUs (access points), mobile vehicle stations, OVS backhaul switch,
safety server + infotainment server, RYU as external OpenFlow 1.3 controller.

Order: mn -c  ->  ryu-manager ryu.app.simple_switch_13 --verbose  ->  python3 v2x_topology.py
"""
from mininet.log import setLogLevel, info
from mininet.node import RemoteController, OVSKernelSwitch
from mn_wifi.net import Mininet_wifi
from mn_wifi.cli import CLI
from mn_wifi.link import wmediumd
from mn_wifi.wmediumdConnector import interference


def topology():
    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference)

    info('*** Adding controller (RYU, remote, OpenFlow 1.3)\n')
    c0 = net.addController('c0', controller=RemoteController,
                           ip='127.0.0.1', port=6653)

    info('*** Adding access points (RSUs)\n')
    rsu1 = net.addAccessPoint('rsu1', ssid='rsu1-ssid', mode='g',
                              channel='1', position='15,30,0',
                              protocols='OpenFlow13')
    rsu2 = net.addAccessPoint('rsu2', ssid='rsu2-ssid', mode='g',
                              channel='6', position='55,30,0',
                              protocols='OpenFlow13')

    info('*** Adding OVS backhaul switch\n')
    s1 = net.addSwitch('s1', cls=OVSKernelSwitch, protocols='OpenFlow13')

    info('*** Adding vehicle stations\n')
    veh1 = net.addStation('veh1', mac='00:00:00:00:00:01',
                          ip='10.0.0.1/8', position='10,30,0')
    veh2 = net.addStation('veh2', mac='00:00:00:00:00:02',
                          ip='10.0.0.2/8', position='10,40,0')

    info('*** Adding safety and infotainment servers\n')
    safety_srv = net.addHost('safety', ip='10.0.0.10/8')
    info_srv = net.addHost('infotain', ip='10.0.0.20/8')

    info('*** Setting propagation model\n')
    net.setPropagationModel(model='logDistance', exp=5)

    info('*** Configuring nodes\n')
    net.configureNodes()

    info('*** Creating links\n')
    net.addLink(rsu1, s1)
    net.addLink(rsu2, s1)
    net.addLink(s1, safety_srv)
    net.addLink(s1, info_srv)

    info('*** Plotting topology (live 2D view)\n')
    net.plotGraph(max_x=100, max_y=100)

    info('*** Scripting vehicle mobility (veh1 crosses rsu1 -> rsu2)\n')
    net.startMobility(time=0)
    net.mobility(veh1, 'start', time=1, position='10,30,0')
    net.mobility(veh2, 'start', time=2, position='10,40,0')
    net.mobility(veh1, 'stop', time=20, position='60,30,0')
    net.mobility(veh2, 'stop', time=20, position='50,40,0')
    net.stopMobility(time=21)

    info('*** Starting network\n')
    net.build()
    c0.start()
    rsu1.start([c0])
    rsu2.start([c0])
    s1.start([c0])

    info('*** Running CLI\n')
    CLI(net)

    info('*** Stopping network\n')
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    topology()
