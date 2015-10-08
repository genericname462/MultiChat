# coding=utf-8
import asyncio
import logging
import queue
import socket
import ssl
import sys
import threading
from ast import literal_eval
from typing import Union, ByteString, List, Tuple, Dict
import bson
from struct import unpack

import time


class ChatClient:
    def __init__(self, ):
        """
        Example Client implementation which simply reads stuff from stdin and feeds it to the ChatClientProtocol.
        Reachieved messages get printed to stdout.
        The threading hack is necessary since windows' select/poll does not work on fd's. In a real client the GUI
        would handle that.
        """
        self.instance = ...  # type: ChatClientProtocol
        self.message_q = queue.Queue()
        self.input_thread = ...  # type: threading.Thread
        self.running = False

    def wrap_input(self, q: queue.Queue):
        while self.running:
            try:
                user_input = input() + "\n"
                q.put(user_input)
            except EOFError:
                self.running = False

    async def run(self):
        self.running = True
        self.input_thread = threading.Thread(target=self.wrap_input, args=(self.message_q,))
        self.input_thread.start()
        while self.running:
            try:
                elem = self.message_q.get_nowait()
                self.instance.send_raw(elem)
            except queue.Empty:
                await asyncio.sleep(1)
        self.input_thread.join()

    def shutdown(self):
        self.instance.disconnect()
        self.running = False

    async def add_instance(self, instance):
        self.instance = instance

    async def remove_instance(self):
        self.instance = None

    async def got_message(self, message: Dict):
        print("[{}]{}:{}".format(message["channel"], message["sendername"], message["message"]))


class ChatClientProtocol(asyncio.Protocol):
    def __init__(self, client: ChatClient):
        self.client = client
        self.transport = ...  # type: Union[asyncio.BaseTransport, asyncio.ReadTransport, asyncio.WriteTransport]
        self.servername = ...
        self.buffer = bytearray()

    def connection_made(self, transport: Union[asyncio.BaseTransport, asyncio.ReadTransport, asyncio.WriteTransport]):
        self.transport = transport
        self.servername = str(transport.get_extra_info("peername"))
        logging.info("Connected to {}".format(self.servername))
        asyncio.ensure_future(self.client.add_instance(self))

    def connection_lost(self, exc):
        logging.info("Lost connection to {}".format(self.servername))
        asyncio.ensure_future(self.client.remove_instance())

    def data_received(self, data: ByteString):
        # TODO: Handle incomplete transmissions
        logging.debug("Got raw data {!r} from {}".format(data, self.servername))
        self.buffer.extend(data)
        logging.debug("Buffer contains {!r}".format(self.buffer))

        if len(self.buffer) >= 4:
            bson_expected_len = unpack("<i", self.buffer[:4])[0]
            if len(self.buffer) >= bson_expected_len:
                bson_obj = self.buffer[:bson_expected_len]  # contains the (hopefully) valid BSON object
                self.buffer = self.buffer[bson_expected_len:]  # shifts the buffer to the start of the next object
                try:
                    t = time.clock()
                    message = bson.loads(bson_obj)
                    delta = time.clock() - t
                    logging.debug("Decoded {} from {}, took {} s".format(message, self.servername, delta))
                    asyncio.ensure_future(self.client.got_message(message))
                except IndexError as e:
                    logging.warning("{}: BSONDecodeError: {}".format(self.servername, e))
                    pass

    def send_message(self, channel: str, message: str):
        formatted = bson.dumps({"channel": channel, "message": message})
        logging.debug("Send message {!r} to {}".format(formatted, self.servername))
        self.transport.write(formatted)

    def send_raw(self, message):
        message_dict = literal_eval(message)
        message_bson = bson.dumps(message_dict)
        logging.debug("Send raw message {!r} to {}".format(message, self.servername))
        self.transport.write(message_bson)

    def disconnect(self):
        logging.info("Disconnecting from {}".format(self.servername))
        self.transport.close()


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("{} {} {}".format(sys.argv[0], "ip", "port"))
        sys.exit(1)
    host = sys.argv[1]
    port = int(sys.argv[2])

    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.load_verify_locations(cafile="ssl/cert.pem")

    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    myclient = ChatClient()
    asyncio.ensure_future(myclient.run())

    coro = loop.create_connection(lambda: ChatClientProtocol(myclient),
                                  host, port,
                                  family=socket.AF_INET,
                                  ssl=ssl_ctx
                                  )
    (client_transport, client_protocol) = loop.run_until_complete(coro)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    myclient.shutdown()
    client_protocol.disconnect()
    loop.close()
