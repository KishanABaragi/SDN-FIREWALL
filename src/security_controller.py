from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp
from ryu.lib import hub
import csv, json, os, re, socket, time
from datetime import datetime

CONTROL_HOST = '127.0.0.1'
CONTROL_PORT = 6001
LOGGER_IP = '10.0.0.4'
LOGGER_PORT = 6000
DEFAULT_BLOCK_SECONDS = 30
SYN_WINDOW_SECONDS = 10
SYN_THRESHOLD = 12

class SecurityController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SecurityController, self).__init__(*args, **kwargs)
        self.mac_to_port, self.datapaths = {}, {}
        self.blocked_macs, self.block_start, self.block_generation = set(), {}, {}
        self.syn_history = {}
        self.log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs', 'controller_events.csv')
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        if not os.path.exists(self.log_path) or os.path.getsize(self.log_path) == 0:
            with open(self.log_path, 'w', newline='') as f:
                csv.writer(f).writerow(['timestamp','action','mac','result','duration_ms','block_seconds','detail'])
        self.control_thread = hub.spawn(self.control_server)

    def emit_event(self, action, mac, detail=''):
        ip = ''
        try:
            # MAC-to-IP is learned from packet-in traffic when available.
            ip = self.mac_to_ip.get(mac, '')
        except Exception:
            pass
        event = {'time': int(time.time()), 'type': action, 'src_ip': ip or 'unknown', 'src_mac': mac,
                 'src_port': 0, 'dst_port': 5000, 'detail': detail}
        try:
            with socket.create_connection((LOGGER_IP, LOGGER_PORT), timeout=1.5) as s:
                s.sendall((json.dumps(event) + '\n').encode())
        except OSError as e:
            self.logger.warning('Logger unavailable for %s event: %s', action, e)

    def log_event(self, action, mac, result, duration_ms='', block_seconds='', detail=''):
        with open(self.log_path, 'a', newline='') as f:
            csv.writer(f).writerow([datetime.now().astimezone().isoformat(timespec='seconds'), action, mac, result, duration_ms, block_seconds, detail])
        self.emit_event(action, mac, detail or result)

    def add_flow(self, dp, priority, match, actions=None, hard_timeout=0):
        parser = dp.ofproto_parser
        instructions = [] if actions is None else [parser.OFPInstructionActions(dp.ofproto.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority, match=match, instructions=instructions, hard_timeout=hard_timeout))

    def install_block_rules(self, dp, mac, seconds=0):
        parser = dp.ofproto_parser
        self.add_flow(dp, 100, parser.OFPMatch(eth_src=mac), hard_timeout=seconds)
        self.add_flow(dp, 100, parser.OFPMatch(eth_dst=mac), hard_timeout=seconds)

    def delete_block_rules(self, dp, mac):
        parser, ofp = dp.ofproto_parser, dp.ofproto
        for match in (parser.OFPMatch(eth_src=mac), parser.OFPMatch(eth_dst=mac)):
            dp.send_msg(parser.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE_STRICT, priority=100,
                out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY, match=match))

    def block_host(self, mac, seconds=DEFAULT_BLOCK_SECONDS, reason='manual request'):
        mac = mac.lower()
        if mac in self.blocked_macs:
            return 'Already blocked: ' + mac
        start = time.perf_counter()
        self.blocked_macs.add(mac)
        self.block_start[mac] = time.perf_counter()
        generation = self.block_generation.get(mac, 0) + 1
        self.block_generation[mac] = generation
        for dp in list(self.datapaths.values()):
            self.install_block_rules(dp, mac, seconds)
        elapsed = (time.perf_counter() - start) * 1000
        self.logger.warning('BLOCK %s for %ss (%s); rule submission %.3f ms', mac, seconds, reason, elapsed)
        self.log_event('BLOCK', mac, 'rules_submitted', '%.3f' % elapsed, seconds, reason)
        hub.spawn_after(seconds, self.expire_block, mac, generation)
        return 'Blocked %s for %ss; controller rule-submission time %.3f ms; auto-unblock scheduled' % (mac, seconds, elapsed)

    def expire_block(self, mac, generation):
        if mac not in self.blocked_macs or self.block_generation.get(mac) != generation:
            return
        for dp in list(self.datapaths.values()):
            self.delete_block_rules(dp, mac)
        self.blocked_macs.discard(mac)
        duration = (time.perf_counter() - self.block_start.pop(mac, time.perf_counter())) * 1000
        self.logger.info('AUTO-UNBLOCK %s after configured timeout; blocked duration %.1f ms', mac, duration)
        self.log_event('UNBLOCK', mac, 'automatic_rules_removed', '', '', 'block timer expired')

    def unblock_host(self, mac):
        mac = mac.lower()
        if mac not in self.blocked_macs:
            return 'Not blocked: ' + mac
        self.block_generation[mac] = self.block_generation.get(mac, 0) + 1
        for dp in list(self.datapaths.values()):
            self.delete_block_rules(dp, mac)
        self.blocked_macs.remove(mac)
        duration = (time.perf_counter() - self.block_start.pop(mac, time.perf_counter())) * 1000
        self.log_event('UNBLOCK', mac, 'manual_rules_removed', '', '', 'manual recovery; blocked duration %.1f ms' % duration)
        return 'Unblocked ' + mac

    def control_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((CONTROL_HOST, CONTROL_PORT)); server.listen(10)
        self.logger.info('Control interface listening on %s:%s', CONTROL_HOST, CONTROL_PORT)
        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    fields = conn.recv(256).decode('utf-8', errors='replace').strip().split()
                    if len(fields) not in (2, 3) or fields[0].upper() not in ('BLOCK','UNBLOCK'):
                        reply = 'Use BLOCK <MAC> [seconds] or UNBLOCK <MAC>'
                    else:
                        action, mac = fields[0].upper(), fields[1].lower()
                        if not re.fullmatch(r'[0-9a-f]{2}(?::[0-9a-f]{2}){5}', mac): reply = 'Invalid MAC address'
                        elif action == 'BLOCK':
                            seconds = int(fields[2]) if len(fields) == 3 else DEFAULT_BLOCK_SECONDS
                            if seconds < 1 or seconds > 3600: reply = 'Block duration must be 1..3600 seconds'
                            else: reply = self.block_host(mac, seconds)
                        else: reply = self.unblock_host(mac)
                    conn.sendall((reply + '\n').encode())
                except Exception as e:
                    self.logger.exception('Control request failed: %s', e)
                    try: conn.sendall(('Control request failed: %s\n' % e).encode())
                    except OSError: pass

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath; self.datapaths[dp.id] = dp
        parser = dp.ofproto_parser
        self.add_flow(dp, 0, parser.OFPMatch(), [parser.OFPActionOutput(dp.ofproto.OFPP_CONTROLLER, dp.ofproto.OFPCML_NO_BUFFER)])
        for mac in self.blocked_macs: self.install_block_rules(dp, mac)
        self.logger.info('Security controller connected to switch %s', dp.id)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER: self.datapaths[dp.id] = dp
        elif ev.state == DEAD_DISPATCHER: self.datapaths.pop(dp.id, None)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg, dp = ev.msg, ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == 0x88cc: return
        src, dst = eth.src.lower(), eth.dst.lower()
        if not hasattr(self, 'mac_to_ip'): self.mac_to_ip = {}
        ip4 = pkt.get_protocol(ipv4.ipv4)
        if ip4: self.mac_to_ip[src] = ip4.src
        if src in self.blocked_macs or dst in self.blocked_macs: return
        # Optional automatic detection: repeated TCP SYN attempts to the application port.
        tcp_pkt = pkt.get_protocol(tcp.tcp)
        if ip4 and tcp_pkt and tcp_pkt.dst_port == 5000 and (tcp_pkt.bits & 0x02):
            now = time.time(); entries = [t for t in self.syn_history.get(src, []) if now - t <= SYN_WINDOW_SECONDS]
            entries.append(now); self.syn_history[src] = entries
            if len(entries) >= SYN_THRESHOLD:
                self.block_host(src, DEFAULT_BLOCK_SECONDS, 'automatic repeated SYN threshold')
                return
        self.mac_to_port.setdefault(dp.id, {})[src] = in_port
        out_port = self.mac_to_port[dp.id].get(dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        # Keep TCP/5000 packets visible to PacketIn so repeated SYN attempts can be counted.
        tcp_for_flow = pkt.get_protocol(tcp.tcp)
        ip_for_flow = pkt.get_protocol(ipv4.ipv4)
        is_app_flow = bool(ip_for_flow and tcp_for_flow and (tcp_for_flow.dst_port == 5000 or tcp_for_flow.src_port == 5000))
        if out_port != ofp.OFPP_FLOOD and not is_app_flow:
            self.add_flow(dp, 1, parser.OFPMatch(in_port=in_port, eth_src=src, eth_dst=dst), actions)
        data = None if msg.buffer_id != ofp.OFP_NO_BUFFER else msg.data
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data))
