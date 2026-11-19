from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel

def create_topology():
    net = Mininet(controller=RemoteController, switch=OVSKernelSwitch)

    print("*** Adding Controller ***")
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6633)

    print("*** Adding Switch and Hosts ***")
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    client = net.addHost('c1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    ds1 = net.addHost('ds1', ip='10.0.0.10/24', mac='00:00:00:00:00:10')
    ds2 = net.addHost('ds2', ip='10.0.0.11/24', mac='00:00:00:00:00:11')

    print("*** Creating Links ***")
    net.addLink(client, s1, port2=1)
    net.addLink(ds1, s1, port2=2)
    net.addLink(ds2, s1, port2=3)

    print("*** Starting Network ***")
    net.start()
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    create_topology()
