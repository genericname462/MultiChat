# coding=utf-8
import asyncio
import json
import logging
import os
import socket
import ssl
from typing import Union, Set, List, Dict, Tuple, ByteString
import sys

welcome_message = "Expected format: utf-8_encoding( json_encoding( [List_of_channels, message] ) + \"\\n\" )\n" + \
    "Example: b\'[[\"global\", \"foo\"], \"Hello, world\\\\nMultiline!\"]\\n\'\n" + \
    "Active channel for now: {}\n" + \
    "Available commands: {}\n"


class Chat:
    def __init__(self):
        self.channels = {"global": set(), "test": set()}  # type: Dict[str: Set["ChatProtocol"]]
        self.queue = asyncio.Queue()

    async def run(self):
        """
        While running the chat will continuously retrieve (instance, message) tuples from the queue and process them.
        """
        logging.info("Chat startup")
        while True:
            (instance, message) = await self.queue.get()
            await self.handle_message(instance, message)

    async def handle_message(self, instance: "ChatServerProtocol", message: Tuple[List[str], str]):
        if message[1].startswith("%"):
            self.handle_command(instance, message[1])
            return
        for channel in message[0]:
            if channel in self.channels:
                for subscriber in self.channels[channel]:
                    subscriber.send_message(channel, instance.peername, message[1])
        pass

    async def add_message(self, instance: "ChatServerProtocol", message: Tuple[List[str], str]):
        """
        Adds a message from instance to the queue.
        """
        await self.queue.put((instance, message))

    def register(self, instance: "ChatServerProtocol"):
        """
        Registers an instance to the chat. Implicates a mandatory subscription to channel "global".
        """
        self.subscribe(instance, ["global"])
        instance.send_message("info",
                              "server",
                              "Hello {}\n{}".format(
                                  instance.peername,
                                  welcome_message.format(self.channels.keys(),
                                                         ["%name", "%join", "%leave", "%new"]
                                                         )
                              ))
        logging.info("Registered {} to chat".format(instance.peername))

    def deregister(self, instance: "ChatServerProtocol"):
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

    def handle_command(self, instance: "ChatServerProtocol", command: str):
        # TODO: stuff like %quit, %kick, ...
        commands = {
            "%name": lambda x: instance.set_name(x),
            "%join": lambda x: self.subscribe(instance, x.split()),
            "%leave": lambda x: self.unsubscribe(instance, x.split()),
            "%new": lambda x: self.create_channel(x)
        }
        try:
            op_code, sep, parameter = command.partition(" ")
            commands[op_code](parameter)
            logging.info("Executed command {} from {}".format((op_code, parameter), instance.peername))
        except (KeyError, TypeError):
            raise NotImplementedError

    def subscribe(self, instance: "ChatServerProtocol", channel_list: List[str]):
        """
        Subscribes an instance to a list of channels. This instance will receive all messages from these channels.
        """
        for channel in channel_list:
            try:
                self.channels[channel].add(instance)
                logging.debug("{} joined channel {}".format(instance.peername, channel))
                instance.send_message("info", "server", "Joined {}".format(channel))
            except KeyError:
                instance.send_message("info", "server", "Channel {} does not exist".format(channel))
                pass

    def unsubscribe(self, instance: "ChatServerProtocol", channel_list: List[str]):
        """
        Unsubscribes an instance from a list of channels. This instance will receive no more messages from these channels.
        """
        for channel in channel_list:
            try:
                self.channels[channel].remove(instance)
                logging.debug("{} left channel {}".format(instance.peername, channel))
                instance.send_message("info", "server", "Left {}".format(channel))
            except KeyError:
                instance.send_message("info", "server", "Channel {} does not exist".format(channel))
                pass

    def create_channel(self, channel_name: str):
        if channel_name not in self.channels:
            self.channels[channel_name] = set()

    def kick(self, instance: "ChatServerProtocol"):
        """
        Similar to deregister() except that the TCP connection gets closed.
        """
        instance.send_message("info", "server", "Kicked. Git Gud")
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


class ChatServerProtocol(asyncio.Protocol):
    def __init__(self, chat: Chat):
        self.chat = chat
        self.transport = ...  # type: Union[asyncio.BaseTransport, asyncio.ReadTransport, asyncio.WriteTransport]
        self.peername = ...
        self.buffer = bytearray()

    def connection_made(self, transport: Union[asyncio.BaseTransport, asyncio.ReadTransport, asyncio.WriteTransport]):
        self.transport = transport
        self.peername = str(transport.get_extra_info("peername"))
        logging.info("Got connection from {}".format(self.peername))
        self.chat.register(self)

    def connection_lost(self, exc):
        logging.info("Lost connection to {}".format(self.peername))
        self.chat.deregister(self)
        self.transport.close()

    def data_received(self, data: ByteString):
        # Expected format: utf-8( json( [List_of_channels, message] ) + "\n" )
        # Example: b'[["global", "foo"], "Hello, world\\nMultiline!"]\n'
        # Meaning: Send "Hello, world\nMultiline!" to channel "global" and "foo", sender gets identified by his socket.
        # The incoming stream will get split at the first occurrence of a "\n" and a decoding attempt will be made.
        # Failure to decode discards the messages up to and including the "\n", so that a clean start for the
        # next message is guaranteed.
        logging.debug("Got raw data {!r} from {}".format(data, self.peername))
        self.buffer.extend(data)
        logging.debug("Buffer of {} contains {!r}".format(self.peername, self.buffer))
        while True:
            complete_message, separator, tail = self.buffer.partition(b"\n")
            if separator:
                self.buffer = tail
                logging.debug("Trying to decode {!r} of {}".format(complete_message, self.peername))
                try:
                    message = json.loads(complete_message.decode())
                    asyncio.ensure_future(self.chat.add_message(self, message))
                except json.JSONDecodeError as e:
                    logging.warning("{}: JSONDecodeError: {}".format(self.peername, e))
                    break
            else:
                break

    def send_message(self, channel: str, peername: str, message: str):
        formatted = json.dumps([channel, peername, message]).encode() + b"\n"
        logging.debug("Send message {!r} to {}".format(formatted, self.peername))
        self.transport.write(formatted)

    def send_raw(self, message):
        logging.debug("Send raw message {!r} to {}".format(message, self.peername))
        self.transport.write(message.encode())

    def disconnect(self):
        logging.info("Disconnecting {}".format(self.peername))
        self.transport.close()

    def set_name(self, new_name):
        if not new_name:
            new_name = self.peername
        logging.info("{} changed name to {}".format(self.peername, new_name))
        self.peername = new_name


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("{} {} {}".format(sys.argv[0], "ip", "port"))
        sys.exit(1)
    host = sys.argv[1]
    port = int(sys.argv[2])

    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

    # CLIENT_AUTH as in Clients will authenticate us
    ssl_ctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
    ssl_ctx.load_cert_chain(certfile="ssl/cert.pem", keyfile="ssl/key.pem")
    ssl_ctx.options |= ssl.OP_NO_SSLv2
    ssl_ctx.options |= ssl.OP_NO_SSLv3
    ssl_ctx.options |= ssl.OP_NO_TLSv1
    ssl_ctx.options |= ssl.OP_NO_TLSv1_1
    ssl_ctx.options |= ssl.PROTOCOL_TLSv1_2

    if os.name == 'nt':
        alt_loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(alt_loop)

    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    mychat = Chat()
    asyncio.ensure_future(mychat.run())

    coro = loop.create_server(lambda: ChatServerProtocol(mychat),
                              host, port,
                              family=socket.AF_INET,
                              reuse_address=True,
                              backlog=1024,
                              ssl=ssl_ctx
                              )
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
