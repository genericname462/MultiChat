# coding=utf-8
import asyncio
import json
import socket
from typing import Union, Set, List, Dict, Tuple


welcome_message = "Expected format: utf-8_encoding( json_encoding( [List_of_channels, message] ) + \"\\n\" )\n" + \
    "Example: b\'[[\"global\", \"foo\"], \"Hello, world\\\\nMultiline!\"]\\n\'\n" + \
    "Active channel for now: \"global\"\n"


class Chat:
    def __init__(self):
        self.channels = {"global": set()}  # type: Dict[str: Set["ChatProtocol"]]

    def register(self, instance: "ChatProtocol"):
        self.subscribe(instance, "global")
        instance.send_raw("Hello {}\n{}".format(instance.peername, welcome_message))

    def deregister(self, instance: "ChatProtocol"):
        for channel_user_list in self.channels.values():
            try:
                channel_user_list.remove(instance)
            except KeyError:
                pass

    def pass_message(self, instance: "ChatProtocol", message: Tuple[List[str], str]):
        if message[1].startswith("%"):
            self.handle_command(instance, message[1])
            return
        for channel in message[0]:
            if channel in self.channels.keys():
                for subscriber in self.channels[channel]:
                    subscriber.send_message(channel, instance.peername, message[1])
        pass

    def handle_command(self, instance: "ChatProtocol", command: str):
        # TODO: stuff like %join, %leave, %quit, %kick, %name
        raise NotImplementedError

    def subscribe(self, instance: "ChatProtocol", channel: str):
        try:
            self.channels[channel].add(instance)
        except KeyError:
            pass

    def unsubscribe(self, instance: "ChatProtocol", channel: str):
        try:
            self.channels[channel].remove(instance)
        except KeyError:
            pass

    def kick(self, instance: "ChatProtocol"):
        instance.send_raw("Git gud!")
        self.deregister(instance)
        instance.disconnect()

    def shutdown(self):
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
        print("Got connection from", self.peername)
        self.chat.register(self)
        print("Registered {} to chat".format(self.peername))

    def connection_lost(self, exc):
        print("Lost connection to", self.peername)
        self.chat.deregister(self)
        print("Deregistered {} from chat".format(self.peername))
        self.transport.close()

    def data_received(self, data):
        # Expected format: utf-8( json( [List_of_channels, message] ) + "\n" )
        # Example: b'[["global", "foo"], "Hello, world\\nMultiline!"]\n'
        # Meaning: Send "Hello, world\nMultiline!" to channel "global" and "foo", sender gets identified by his socket
        # TODO: Assumes only complete and well-formatted transmissions for now
        print("Got raw data {!r} from {}".format(data, self.peername))
        try:
            message = json.loads(data.decode())
            self.chat.pass_message(self, message)
        except json.JSONDecodeError as e:
            print(e)
            pass

    def send_message(self, channel: str, peername: str, message: str):
        formatted = "[{}]{}: {}".format(channel, peername, message)
        self.transport.write(formatted.encode())

    def send_raw(self, message):
        print("Send message {!r} to {}".format(message, self.peername))
        self.transport.write(message.encode())

    def disconnect(self):
        print("Disconnecting {}".format(self.peername))
        self.transport.close()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    host = socket.gethostbyname(socket.gethostname())
    port = 3030
    mychat = Chat()
    coro = loop.create_server(lambda: ChatProtocol(mychat), "127.0.0.1", port, family=socket.AF_INET, reuse_address=True)
    server = loop.run_until_complete(coro)

    print('Serving on {}'.format(server.sockets[0].getsockname()))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    mychat.shutdown()
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
