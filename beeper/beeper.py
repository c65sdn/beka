from gevent.pool import Pool
from gevent.server import StreamServer

from beeper.state_machine import StateMachine
from beeper.peering import Peering

DEFAULT_BGP_PORT = 179

class Beeper(object):
    def __init__(self, local_address, bgp_port, local_as,
            router_id, peer_up_handler, peer_down_handler,
            route_handler, error_handler):
        self.local_address = local_address
        self.bgp_port = bgp_port
        self.local_as = local_as
        self.router_id = router_id
        self.peer_up_handler = peer_up_handler
        self.peer_down_handler = peer_down_handler
        self.route_handler = route_handler
        self.error_handler = error_handler

        self.peers = {}
        self.peerings = []
        self.stream_server = None

        if not self.bgp_port:
            self.bgp_port = DEFAULT_BGP_PORT

    def add_neighbor(self, connect_mode, peer_ip,
            peer_as):
        if connect_mode != "passive":
            raise ValueError("Only passive BGP supported")
        if peer_ip in self.peers:
            raise ValueError("Peer already added: %s %d" % (peer_ip, peer_as))

        self.peers[peer_ip] = {
            "peer_ip": peer_ip,
            "peer_as": peer_as
        }

    def run(self):
        pool = Pool(100)
        self.stream_server = StreamServer((self.local_address, self.bgp_port), self.handle, spawn=pool)
        self.stream_server.serve_forever()

    def handle(self, socket, address):
        peer_ip = address[0]
        if peer_ip not in self.peers:
            self.error_handler("Rejecting connection from %s:%d" % address)
            socket.close()
            return
        peer = self.peers[peer_ip]
        state_machine = StateMachine(
            local_as=self.local_as,
            peer_as=peer["peer_as"],
            router_id=self.router_id,
            local_address=self.local_address,
            neighbor=peer["peer_ip"]
        )
        peering = Peering(state_machine, address, socket, self.route_handler)
        self.peerings.append(peering)
        self.peer_up_handler(peer_ip, peer["peer_as"])
        peering.run()
        self.peer_down_handler(peer_ip, peer["peer_as"])
        self.peerings.remove(peering)

    def shutdown(self):
        if self.stream_server:
            self.stream_server.stop()
        for peering in self.peerings:
            peering.shutdown()
