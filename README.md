Simple TCP/TLS chat with channels using some of the new asyncio features and the new type hints.

### Message format
##### Client to server:
Basic format is a tuple `(channels, message)`, but since JSON has not tuple type, it's a list.
```
[[List of channels you want to send to], message]
```
Let JSON handle the fancy character encoding so stuff like `äöü\n沓` becomes `\\u00e4\\u00f6\\u00fc\\n\\u6c93`.
Notice how the newline got escaped as well, so we use that as a frame delimiter in our TCP stream.
So the whole thing becomes:
```python
json.dumps([[channels], message]).encode() + b"\n"
```
Example:
`[["global"],"foo\nmultiline!"]` -> `b'[["global"], "foo\\nmultiline!"]\n'`
##### Server to client:
For debugging reasons it's a simple utf-8 string at the moment but reusing the upper format should be easy.
```python
b'[channel]peername: message\n'
```

### Security
To run your own server you need a private key and a certificate signing that key:
```bash
openssl req -x509 -nodes -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem
```

Connecting to it netcat style:
```bash
openssl s_client -connect ip:port -CAfile ssl/cert.pem
```