Simple TCP chat with channels using some of the new asyncio features and the new type hints.

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