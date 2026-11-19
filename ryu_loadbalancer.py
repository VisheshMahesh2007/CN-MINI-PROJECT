import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3, ether, inet
from ryu.lib.packet import packet, ethernet, ipv4, udp

DNS_PORT = 5555
CACHE_TTL = 60

CTRL_IP = '10.0.0.254'
CTRL_MAC = '00:00:00:00:00:fe'

SERVERS = {
    2: {'name': 'ds1', 'ip': '10.0.0.10', 'mac': '00:00:00:00:00:10'},
    3: {'name': 'ds2', 'ip': '10.0.0.11', 'mac': '00:00:00:00:00:11'},
}

class DNSLoadBalancer(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(DNSLoadBalancer, self).__init__(*args, **kwargs)
        self.active_servers = sorted(SERVERS.keys())
        self.rr_index = 0
        self.dns_cache = {}
        self.mac_to_port = {}

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match,
                                instructions=inst, idle_timeout=idle_timeout)
        datapath.send_msg(mod)

    def send_packet_out(self, datapath, in_port, actions, data):
        parser = datapath.ofproto_parser
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=datapath.ofproto.OFP_NO_BUFFER,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        to_ctrl = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]

        self.add_flow(datapath, 0, parser.OFPMatch(), to_ctrl)

        dns_query = parser.OFPMatch(eth_type=ether.ETH_TYPE_IP, ip_proto=inet.IPPROTO_UDP,
                                    udp_dst=DNS_PORT)
        dns_reply = parser.OFPMatch(eth_type=ether.ETH_TYPE_IP, ip_proto=inet.IPPROTO_UDP,
                                    udp_src=DNS_PORT)
        self.add_flow(datapath, 100, dns_query, to_ctrl)
        self.add_flow(datapath, 100, dns_reply, to_ctrl)
        self.logger.info("[*] Switch %s connected, DNS interception rules installed",
                         datapath.id)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        ofproto = msg.datapath.ofproto
        port_no = msg.desc.port_no
        if port_no not in SERVERS:
            return

        server = SERVERS[port_no]
        link_down = (msg.reason == ofproto.OFPPR_DELETE or
                     msg.desc.state & ofproto.OFPPS_LINK_DOWN)

        if link_down and port_no in self.active_servers:
            self.active_servers.remove(port_no)
            for table in self.mac_to_port.values():
                for mac in [m for m, p in table.items() if p == port_no]:
                    del table[mac]
            self.logger.info("[!] FAULT DETECTED: Link down on port %s (%s)",
                             port_no, server['name'])
        elif not link_down and port_no not in self.active_servers:
            self.active_servers.append(port_no)
            self.active_servers.sort()
            self.logger.info("[+] RECOVERED: Link up on port %s (%s)",
                             port_no, server['name'])
        else:
            return

        names = [SERVERS[p]['name'] for p in self.active_servers]
        self.logger.info("[*] Active servers: %s", names if names else "none")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether.ETH_TYPE_LLDP:
            return

        self.mac_to_port.setdefault(datapath.id, {})[eth.src] = in_port

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        udp_pkt = pkt.get_protocol(udp.udp)

        if ip_pkt and udp_pkt and udp_pkt.dst_port == DNS_PORT:
            self.handle_query(datapath, in_port, msg.data, eth, ip_pkt, udp_pkt, pkt)
        elif ip_pkt and udp_pkt and udp_pkt.src_port == DNS_PORT:
            self.handle_reply(datapath, in_port, msg.data, eth, pkt)
        else:
            self.l2_forward(datapath, in_port, msg.data, eth)

    def get_payload(self, pkt):
        payload = pkt.protocols[-1]
        if not isinstance(payload, (bytes, bytearray)):
            return ''
        return payload.decode('utf-8', errors='ignore').strip('\x00').strip()

    def handle_query(self, datapath, in_port, data, eth, ip_pkt, udp_pkt, pkt):
        parser = datapath.ofproto_parser
        domain = self.get_payload(pkt)
        if not domain:
            return

        entry = self.dns_cache.get(domain)
        if entry and time.time() - entry[1] < CACHE_TTL:
            self.logger.info("[+] CACHE HIT: %s -> %s (served by controller)", domain, entry[0])
            reply = self.build_reply(eth, ip_pkt, udp_pkt, "%s: %s" % (domain, entry[0]))
            self.send_packet_out(datapath, datapath.ofproto.OFPP_CONTROLLER,
                                 [parser.OFPActionOutput(in_port)], reply)
            return
        if entry:
            del self.dns_cache[domain]

        if not self.active_servers:
            self.logger.info("[-] No active servers available, dropping query for %s", domain)
            return

        port = self.active_servers[self.rr_index % len(self.active_servers)]
        self.rr_index += 1
        server = SERVERS[port]
        self.logger.info("[*] CACHE MISS: %s -> forwarding to %s (%s)",
                         domain, server['name'], server['ip'])

        actions = [parser.OFPActionSetField(eth_dst=server['mac']),
                   parser.OFPActionSetField(ipv4_dst=server['ip']),
                   parser.OFPActionOutput(port)]
        self.send_packet_out(datapath, in_port, actions, data)

    def handle_reply(self, datapath, in_port, data, eth, pkt):
        parser = datapath.ofproto_parser
        text = self.get_payload(pkt)
        if ':' in text:
            domain, ip = [part.strip() for part in text.split(':', 1)]
            if ip != 'NXDOMAIN':
                self.dns_cache[domain] = (ip, time.time())
                self.logger.info("[*] CACHED: %s -> %s", domain, ip)

        out_port = self.mac_to_port.get(datapath.id, {}).get(eth.dst,
                                                            datapath.ofproto.OFPP_FLOOD)
        self.send_packet_out(datapath, in_port, [parser.OFPActionOutput(out_port)], data)

    def build_reply(self, eth, ip_pkt, udp_pkt, text):
        reply = packet.Packet()
        reply.add_protocol(ethernet.ethernet(ethertype=ether.ETH_TYPE_IP,
                                             dst=eth.src, src=CTRL_MAC))
        reply.add_protocol(ipv4.ipv4(proto=inet.IPPROTO_UDP, src=CTRL_IP, dst=ip_pkt.src))
        reply.add_protocol(udp.udp(src_port=DNS_PORT, dst_port=udp_pkt.src_port))
        reply.add_protocol(text.encode())
        reply.serialize()
        return reply.data

    def l2_forward(self, datapath, in_port, data, eth):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        out_port = self.mac_to_port[datapath.id].get(eth.dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_src=eth.src, eth_dst=eth.dst)
            self.add_flow(datapath, 1, match, actions, idle_timeout=30)

        self.send_packet_out(datapath, in_port, actions, data)
