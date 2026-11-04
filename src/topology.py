from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel

class FirewallTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        roles = {1:'client1', 2:'client2_test', 3:'app_server', 4:'event_logger', 5:'client3', 6:'client4'}
        for i in range(1, 7):
            h = self.addHost('h%d' % i, ip='10.0.0.%d/8' % i, mac='00:00:00:00:00:%02x' % i)
            self.addLink(h, s1)

def main():
    net = Mininet(topo=FirewallTopo(), controller=None, autoSetMacs=False)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    net.start()
    print('Six-host SDN firewall topology running. Roles: h1/h2/h5/h6 clients, h3 app server, h4 logger.')
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    main()
