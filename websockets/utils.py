import struct
import os

def encode_websocket_frame(message: str) -> bytearray:
    """Encodes a WebSocket text frame."""
    message_bytes = message.encode()
    frame = bytearray([0b10000001])  # FIN=1, Opcode=0x1 (text)

    length = len(message_bytes)
    if length < 126:
        frame.append(length | 0b10000000)  # Set MASK bit
    elif length < (1 << 16):
        frame.append(126 | 0b10000000)
        frame.extend(struct.pack(">H", length))
    else:
        frame.append(127 | 0b10000000)
        frame.extend(struct.pack(">Q", length))

    # Generate a 4-byte masking key (WebSocket spec requires masking from client)
    mask_key = os.urandom(4)
    frame.extend(mask_key)

    # Mask the payload
    masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(message_bytes))
    frame.extend(masked_payload)

    return frame

def unpack_websocket_frame(frame: bytearray) -> tuple[int, bytearray]:
    """Receives a WebSocket frame from the server."""
    opcode = frame[0] & 0b00001111  # Extract opcode
    payload_length = frame[1] & 0b01111111  # Extract payload length
    payload_start = 2

    if payload_length == 126:
        payload_length = struct.unpack(">H", frame[2:4])[0]
        payload_start = 4
    elif payload_length == 127:
        payload_length = struct.unpack(">Q", frame[2:10])[0]
        payload_start = 10

    payload = frame[payload_start:payload_start + payload_length]

    return opcode, payload

def create_pong_frame(payload: bytearray) -> bytearray:
    """Sends a properly masked WebSocket pong frame from the client."""
    masking_key = os.urandom(4)  # Generate a 4-byte random masking key

    # Mask the payload (XOR with masking key)
    masked_payload = bytes(payload[i] ^ masking_key[i % 4] for i in range(len(payload)))

    frame = bytearray([0b10001010])  # FIN=1, Opcode=0xA (Pong)
    frame.append(0b10000000 | len(payload))  # Mask bit set (1000 0000) + Payload length
    frame.extend(masking_key)  # Append the masking key
    frame.extend(masked_payload)  # Append masked payload
    return frame
