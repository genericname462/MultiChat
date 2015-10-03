# coding=utf-8
import asyncio
import json
import logging
import socket
import ssl
import sys
from typing import Union, ByteString, List


def pack_message(channels: List[str], message: str) -> ByteString:
    try:
        formatted = json.dumps([channels, message]).encode() + b"\n"
        return formatted
    except TypeError as e:
        logging.error("Error encoding message {}".format(channels, message))
        raise e


class ChatClientProtocol(asyncio.Protocol):
    def __init__(self):
        self.transport = ...  # type: Union[asyncio.BaseTransport, asyncio.ReadTransport, asyncio.WriteTransport]
        self.servername = ...

    def connection_made(self, transport: Union[asyncio.BaseTransport, asyncio.ReadTransport, asyncio.WriteTransport]):
        self.transport = transport
        self.servername = str(transport.get_extra_info("peername"))
        logging.info("Connected to {}".format(self.servername))

    def connection_lost(self, exc):
        logging.info("Lost connection to {}".format(self.servername))

    def data_received(self, data: ByteString):
        logging.debug("Got raw data {!r} from {}".format(data, self.servername))
        pass

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

    coro = loop.create_connection(ChatClientProtocol, host, port, family=socket.AF_INET, ssl=ssl_ctx)
    (client_transport, client_protocol) = loop.run_until_complete(coro)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    client_protocol.disconnect()
    loop.close()
