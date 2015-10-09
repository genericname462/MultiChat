Simple TCP/TLS chat with channels using some of the new asyncio features and the new type hints.

### Message format
Basic format is a BSON dictionary `{key: value}` containing the following requiered keys. Additional keys, e.g. for
file transfer, can be added if needed.

##### Client to server:
```
{
    "channels": [List_of_channels],
    "message": message
}
```
BSON only allows utf-8 strings, so both the channel names and the message are utf-8 encoded.
Example:
`bson.dumps({"channels": ["global"], "message": "Hello, world\nMultiline!"})`

##### Server to client:
Analog to the c2s format, the server to client format contains an additional key `sendername` and reduced the channel
list to a single channel.
```
{
    "channel": channel_name,
    "sendername": name,
    "message": message
}
```

### Security
To run your own server you need a private key and a certificate signing that key:
```bash
openssl req -x509 -nodes -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem
```

Connecting to the server netcat style:
```bash
openssl s_client -connect ip:port -CAfile ssl/cert.pem
```