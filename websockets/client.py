from .utils import encode_websocket_frame, unpack_websocket_frame, create_pong_frame, create_close_frame
from .exceptions import InvalidHanshake, ExceededRetryLimit

import socketpool
import binascii
import warnings
import errno
import wifi
import time
import os


class ClientConnection:
    def __init__(
        self,
        ip_address: str,
        port: int,
        sock: socketpool.Socket | wifi.Radio,
        timeout = 0.01,
        encoding: str = 'utf-8',
        retries: int = 5,
        init_connection_timeout = 1,
    ):
        self.ip_address = ip_address
        self.port = port
        self.sock = sock
        if isinstance(self.sock, wifi.Radio):
            pool = socketpool.SocketPool(wifi.radio)
            self.sock = pool.socket()
        if not isinstance(self.sock, socketpool.Socket):
            raise TypeError(
                f"sock must be a socketpool.Socket or wifi.Radio type not: {type(sock)}"
            )
        self.timeout = timeout
        self.encoding = encoding
        self.retries = retries
        self.init_connection_time = init_connection_timeout
        self.closed = False

    def start_connection_to_server(self):
        self.sock.settimeout(self.init_connection_time)
        self.sock.connect((self.ip_address, self.port))
        self.sock.settimeout(self.timeout)

    def handshake(self):
        websocket_key = binascii.b2a_base64(os.urandom(16), newline=False).decode('utf-8')
        self.raw_send((
              f"GET / HTTP/1.1\r\n"
            + f"Host: {self.ip_address}:{self.port}\r\n" # NOTE: Omitting the + causes a syntax error in CircuitPython
            + f"Upgrade: websocket\r\n"
            + f"Connection: Upgrade\r\n"
            + f"Sec-WebSocket-Key: {websocket_key}\r\n"
            + f"Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode(self.encoding))

        for _ in range(self.retries):
            try:
                buffer = bytearray(1024)
                length = self.sock.recv_into(buffer)
                response = buffer[:length]
                if b"101 Switching Protocols" not in response:
                    raise InvalidHanshake(
                        f'Received the following response:\n{response}'
                    )
                return response.decode('utf-8')
            except OSError as err:
                if err.errno != errno.ETIMEDOUT:
                    raise
        raise ExceededRetryLimit(
            f"Failed to read data after {self.retries} tries"
        )

    def raw_send(self, payload: bytes | bytearray):
        off = 0
        while off < len(payload):
            ret = self.sock.send(payload[off:])
            # print('raw sent!!!')
            if ret is not None:
                off += ret

    def connect(self):
        self.start_connection_to_server()
        handshake_reply = self.handshake()

    def send(self, message: str):
        frame = encode_websocket_frame(message)
        self.raw_send(frame)

    def close(self, code: int = 1000, reason: str = '', sleep: float | None = 0.5):
        self.raw_send(create_close_frame(code, reason))
        self.closed = True
        if sleep:
            time.sleep(sleep) # sleep just to make sure that the close frame is sent properly.
        self.sock.close()

    def __iter__(self):
        while not self.closed:
            try:
                buffer = bytearray(1024)
                length = self.sock.recv_into(buffer)
                frame = buffer[:length]
                opcode, payload = unpack_websocket_frame(frame)
                if opcode == 9:
                    pong_frame = create_pong_frame(payload)
                    self.raw_send(pong_frame)
                    yield None
                elif opcode == 8:
                    self.closed = True
                    break
                elif opcode == 0:
                    warnings.warn('Received a multi-length frame, ignore this.')
                    yield None
                elif opcode <= 2:
                    yield payload
            except OSError as err:
                if err.errno != errno.ETIMEDOUT:
                    raise
                yield None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if not self.closed:
            self.close()
