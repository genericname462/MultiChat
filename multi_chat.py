# coding=utf-8
import asyncio
import json
import logging
import socket
from typing import Union, Set, List, Dict, Tuple

import sys

welcome_message = "Expected format: utf-8_encoding( json_encoding( [List_of_channels, message] ) + \"\\n\" )\n" + \
    "Example: b\'[[\"global\", \"foo\"], \"Hello, world\\\\nMultiline!\"]\\n\'\n" + \
    "Active channel for now: \"global\"\n"


class Chat:
    def __init__(self):
        self.channels = {"global": set()}  # type: Dict[str: Set["ChatProtocol"]]
        self.queue = asyncio.Queue()

    async def run(self):
        """
        While running the chat will continuously retrieve (instance, message) tuples from the queue and process them.
        """
        logging.info("Chat startup")
        while True:
            (instance, message) = await self.queue.get()
            await self.handle_message(instance, message)

    async def handle_message(self, instance: "ChatProtocol", message: Tuple[List[str], str]):
        if message[1].startswith("%"):
            self.handle_command(instance, message[1])
            return
        for channel in message[0]:
            if channel in self.channels.keys():
                for subscriber in self.channels[channel]:
                    subscriber.send_message(channel, instance.peername, message[1])
        pass

    async def add_message(self, instance, message):
        """
        Adds a message from instance to the queue.
        """
        await self.queue.put((instance, message))

    def register(self, instance: "ChatProtocol"):
        """
        Registers an instance to the chat. Implicates a mandatory subscription to channel "global".
        """
        self.subscribe(instance, "global")
        instance.send_raw("Hello {}\n{}".format(instance.peername, welcome_message))
        logging.info("Registered {} to chat".format(instance.peername))

    def deregister(self, instance: "ChatProtocol"):
        """
        Deregisters an instance from chat and all channels. No more messages from that instance will get processed,
        until register() is called again. The TCP connection is left intact.
        """
        for channel_user_list in self.channels.values():
            try:
                channel_user_list.remove(instance)
            except KeyError:
                pass
        logging.info("Deregistered {} from chat".format(instance.peername))

    def handle_command(self, instance: "ChatProtocol", command: str):
        # TODO: stuff like %join, %leave, %quit, %kick, %name
        raise NotImplementedError

    def subscribe(self, instance: "ChatProtocol", channel: str):
        """
        Subscribes an instance to a channel. This instance will receive all messages from that channel.
        """
        try:
            self.channels[channel].add(instance)
        except KeyError:
            pass

    def unsubscribe(self, instance: "ChatProtocol", channel: str):
        """
        Unsubscribes an instance from a channel. This instance will receive no more messages from that channel.
        """
        try:
            self.channels[channel].remove(instance)
        except KeyError:
            pass

    def kick(self, instance: "ChatProtocol"):
        """
        Similar to deregister() except that the TCP connection gets closed.
        """
        instance.send_raw("Git gud!")
        self.deregister(instance)
        instance.disconnect()

    def shutdown(self):
        """
        Shuts the chat down. Every connection will get disconnected. All channels flushed.
        """
        logging.warning("Chat shutdown")
        for subscriber in self.channels["global"]:
            subscriber.disconnect()
        for channel in self.channels.values():
            channel.clear()


class ChatProtocol(asyncio.Protocol):
    def __init__(self, chat: Chat):
        self.chat = chat
        self.transport = ...  # type: Union[asyncio.BaseTransport, asyncio.ReadTransport, asyncio.WriteTransport]
        self.peername = ...

    def connection_made(self, transport: Union[asyncio.BaseTransport, asyncio.ReadTransport, asyncio.WriteTransport]):
        self.transport = transport
        self.peername = str(transport.get_extra_info("peername"))
        logging.info("Got connection from {}".format(self.peername))
        self.chat.register(self)

    def connection_lost(self, exc):
        logging.info("Lost connection to {}".format(self.peername))
        self.chat.deregister(self)
        self.transport.close()

    def data_received(self, data):
        # Expected format: utf-8( json( [List_of_channels, message] ) + "\n" )
        # Example: b'[["global", "foo"], "Hello, world\\nMultiline!"]\n'
        # Meaning: Send "Hello, world\nMultiline!" to channel "global" and "foo", sender gets identified by his socket
        # TODO: Assumes only complete and well-formatted transmissions for now
        logging.info("Got raw data {!r} from {}".format(data, self.peername))
        try:
            message = json.loads(data.decode())
            asyncio.ensure_future(self.chat.add_message(self, message))
        except json.JSONDecodeError as e:
            logging.warning("{}: JSONDecodeError: {}".format(self.peername, e))
            pass

    def send_message(self, channel: str, peername: str, message: str):
        formatted = "[{}]{}: {}\n".format(channel, peername, message)
        logging.info("Send message {!r} to {}".format(formatted, self.peername))
        self.transport.write(formatted.encode())

    def send_raw(self, message):
        logging.info("Send raw message {!r} to {}".format(message, self.peername))
        self.transport.write(message.encode())

    def disconnect(self):
        logging.info("Disconnecting {}".format(self.peername))
        self.transport.close()


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("{} {} {}".format(sys.argv[0], "ip", "port"))
        sys.exit()
    host = sys.argv[1]
    port = int(sys.argv[2])

    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    mychat = Chat()
    asyncio.ensure_future(mychat.run())

    coro = loop.create_server(lambda: ChatProtocol(mychat), host, port, family=socket.AF_INET, reuse_address=True)
    server = loop.run_until_complete(coro)

    logging.info('Serving on {}'.format(server.sockets[0].getsockname()))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    mychat.shutdown()
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
