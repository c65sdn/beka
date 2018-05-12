from eventlet import sleep, GreenPool
from eventlet.queue import Queue
import eventlet.greenthread as greenthread

from .chopper import Chopper
from .event import EventTimerExpired, EventMessageReceived
from .bgp_message import BgpMessage, parse_bgp_message
from .route import RouteAddition, RouteRemoval
from .error import SocketClosedError

import time

class Peering(object):
    def __init__(self, state_machine, peer_address, socket, route_handler):
        self.state_machine = state_machine
        self.peer_address = peer_address[0]
        self.peer_port = peer_address[1]
        self.socket = socket
        self.route_handler = route_handler

    def run(self):
        self.input_stream = self.socket.makefile(mode="rb")
        self.chopper = Chopper(self.input_stream)
        self.pool = GreenPool()
        self.eventlets = []

        self.eventlets.append(self.pool.spawn(self.send_messages))
        self.eventlets.append(self.pool.spawn(self.print_route_updates))
        self.eventlets.append(self.pool.spawn(self.kick_timers))
        self.eventlets.append(self.pool.spawn(self.receive_messages))

        self.pool.waitall()

    def receive_messages(self):
        while True:
            sleep(0)
            try:
                message_type, serialised_message = self.chopper.next()
            except SocketClosedError as e:
                self.shutdown()
                break
            message = parse_bgp_message(message_type, serialised_message)
            event = EventMessageReceived(message)
            tick = int(time.time())
            self.state_machine.event(event, tick)

    def send_messages(self):
        while True:
            sleep(0)
            message = self.state_machine.output_messages.get()
            self.socket.send(BgpMessage.pack(message))

    def print_route_updates(self):
        while True:
            sleep(0)
            route_update = self.state_machine.route_updates.get()
            self.route_handler(route_update)

    def kick_timers(self):
        while True:
            sleep(1)
            tick = int(time.time())
            self.state_machine.event(EventTimerExpired(), tick)

    def shutdown(self):
        for eventlet in self.eventlets:
            eventlet.kill()
