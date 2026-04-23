"""
WebSocket Handler Skill
WebSocket client for real-time communication.
"""

import asyncio
import json
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from collections import deque

METADATA = {
    "name": "websocket-handler",
    "description": "WebSocket client for real-time bidirectional communication",
    "category": "web",
    "version": "1.0.0",
    "author": "Sentience Team",
    "triggers": ["websocket", "ws", "real-time", "socket"],
    "dependencies": [],
    "tags": ["websocket", "real-time", "streaming", "socket"]
}

SKILL_NAME = "websocket-handler"
SKILL_DESCRIPTION = METADATA["description"]
SKILL_CATEGORY = "web"
SKILL_TRIGGERS = METADATA["triggers"]
SKILL_TAGS = METADATA["tags"]


@dataclass
class WebSocketMessage:
    type: str  # 'text', 'binary', 'json'
    content: Any
    timestamp: float


class SimpleWebSocketClient:
    """
    Simple WebSocket client implementation.
    Uses asyncio for async operations.
    """
    
    def __init__(self, url: str, headers: Dict[str, str] = None):
        self.url = url
        self.headers = headers or {}
        self.connected = False
        self.message_queue: deque = deque(maxlen=100)
        self._reader = None
        self._writer = None
    
    async def connect(self) -> bool:
        """Connect to WebSocket server."""
        try:
            # Parse URL
            import urllib.parse
            parsed = urllib.parse.urlparse(self.url)
            
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == 'wss' else 80)
            path = parsed.path or '/'
            
            if parsed.query:
                path += f'?{parsed.query}'
            
            # Open TCP connection
            self._reader, self._writer = await asyncio.open_connection(host, port)
            
            # Send WebSocket handshake
            import hashlib
            import base64
            import os
            
            key = base64.b64encode(os.urandom(16)).decode()
            
            handshake = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Upgrade: websocket\r\n"
                f"Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n"
            )
            
            for k, v in self.headers.items():
                handshake += f"{k}: {v}\r\n"
            
            handshake += "\r\n"
            
            self._writer.write(handshake.encode())
            await self._writer.drain()
            
            # Read response
            response = await self._reader.read(1024)
            
            if b'101' in response and b'Switching Protocols' in response:
                self.connected = True
                return True
            else:
                return False
        
        except Exception as e:
            self.connected = False
            return False
    
    async def send(self, message: Any, message_type: str = 'text') -> bool:
        """Send a message through WebSocket."""
        if not self.connected:
            return False
        
        try:
            if message_type == 'json':
                message = json.dumps(message)
                message_type = 'text'
            
            if isinstance(message, str):
                # Text frame (opcode 0x01)
                data = message.encode('utf-8')
                frame = self._build_frame(0x01, data)
            else:
                # Binary frame (opcode 0x02)
                frame = self._build_frame(0x02, message)
            
            self._writer.write(frame)
            await self._writer.drain()
            return True
        
        except Exception as e:
            return False
    
    def _build_frame(self, opcode: int, data: bytes, mask: bool = True) -> bytes:
        """Build a WebSocket frame."""
        import os
        
        frame = bytearray()
        
        # FIN + opcode
        frame.append(0x80 | opcode)
        
        # Payload length
        length = len(data)
        if mask:
            frame[0] |= 0x00  # Client should mask
        
        if length <= 125:
            frame.append(length if not mask else length | 0x80)
        elif length <= 65535:
            frame.append(126 if not mask else 126 | 0x80)
            frame.extend(length.to_bytes(2, 'big'))
        else:
            frame.append(127 if not mask else 127 | 0x80)
            frame.extend(length.to_bytes(8, 'big'))
        
        # Masking key
        if mask:
            masking_key = os.urandom(4)
            frame.extend(masking_key)
            
            # Mask data
            masked_data = bytearray()
            for i, byte in enumerate(data):
                masked_data.append(byte ^ masking_key[i % 4])
            frame.extend(masked_data)
        else:
            frame.extend(data)
        
        return bytes(frame)
    
    async def receive(self, timeout: float = None) -> Optional[WebSocketMessage]:
        """Receive a message from WebSocket."""
        if not self.connected:
            return None
        
        try:
            # Read frame header
            header = await asyncio.wait_for(self._reader.read(2), timeout)
            
            if len(header) < 2:
                return None
            
            fin = (header[0] & 0x80) != 0
            opcode = header[0] & 0x0F
            masked = (header[1] & 0x80) != 0
            length = header[1] & 0x7F
            
            # Read extended length
            if length == 126:
                ext_length = await self._reader.read(2)
                length = int.from_bytes(ext_length, 'big')
            elif length == 127:
                ext_length = await self._reader.read(8)
                length = int.from_bytes(ext_length, 'big')
            
            # Read masking key
            masking_key = b''
            if masked:
                masking_key = await self._reader.read(4)
            
            # Read payload
            payload = await self._reader.read(length)
            
            # Unmask if needed
            if masked:
                payload = bytes(b ^ masking_key[i % 4] for i, b in enumerate(payload))
            
            import time
            timestamp = time.time()
            
            # Handle opcode
            if opcode == 0x01:  # Text
                text = payload.decode('utf-8')
                
                # Try to parse as JSON
                try:
                    content = json.loads(text)
                    return WebSocketMessage('json', content, timestamp)
                except json.JSONDecodeError:
                    return WebSocketMessage('text', text, timestamp)
            
            elif opcode == 0x02:  # Binary
                return WebSocketMessage('binary', payload, timestamp)
            
            elif opcode == 0x08:  # Close
                await self.close()
                return None
            
            elif opcode == 0x09:  # Ping
                await self._send_pong(payload)
                return await self.receive(timeout)
            
            elif opcode == 0x0A:  # Pong
                return await self.receive(timeout)
            
            return None
        
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            return None
    
    async def _send_pong(self, payload: bytes):
        """Send pong response."""
        frame = self._build_frame(0x0A, payload, mask=False)
        self._writer.write(frame)
        await self._writer.drain()
    
    async def close(self):
        """Close WebSocket connection."""
        if self.connected:
            # Send close frame
            try:
                close_frame = self._build_frame(0x08, b'', mask=True)
                self._writer.write(close_frame)
                await self._writer.drain()
            except:
                pass
            
            self.connected = False
            
            if self._writer:
                self._writer.close()
                try:
                    await self._writer.wait_closed()
                except:
                    pass
    
    async def listen(self, callback: Callable[[WebSocketMessage], None], 
                    max_messages: int = None):
        """Listen for messages and call callback."""
        count = 0
        
        while self.connected:
            if max_messages and count >= max_messages:
                break
            
            message = await self.receive()
            
            if message:
                callback(message)
                count += 1
            elif not self.connected:
                break


class WebSocketConnection:
    """Manage a WebSocket connection with message queue."""
    
    def __init__(self, url: str, headers: Dict[str, str] = None):
        self.url = url
        self.headers = headers
        self.client = SimpleWebSocketClient(url, headers)
        self.messages: deque = deque(maxlen=100)
    
    async def connect(self) -> bool:
        """Connect to server."""
        return await self.client.connect()
    
    async def send_text(self, message: str) -> bool:
        """Send text message."""
        return await self.client.send(message, 'text')
    
    async def send_json(self, data: Dict) -> bool:
        """Send JSON message."""
        return await self.client.send(data, 'json')
    
    async def send_binary(self, data: bytes) -> bool:
        """Send binary message."""
        return await self.client.send(data, 'binary')
    
    async def receive(self, timeout: float = None) -> Optional[WebSocketMessage]:
        """Receive next message."""
        return await self.client.receive(timeout)
    
    async def close(self):
        """Close connection."""
        await self.client.close()
    
    def get_messages(self, n: int = None) -> List[WebSocketMessage]:
        """Get received messages."""
        if n:
            return list(self.messages)[-n:]
        return list(self.messages)


def execute(
    url: str,
    operation: str = "connect",
    message: Any = None,
    message_type: str = "text",
    timeout: float = None,
    headers: Dict[str, str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    WebSocket operations.
    
    Args:
        url: WebSocket URL (ws:// or wss://)
        operation: Operation (connect/send/receive/close)
        message: Message to send
        message_type: Message type (text/json/binary)
        timeout: Receive timeout in seconds
        headers: Custom headers
    
    Returns:
        Operation result
    """
    
    async def run():
        client = SimpleWebSocketClient(url, headers)
        
        if operation == "connect":
            connected = await client.connect()
            return {
                "success": connected,
                "connected": connected,
                "url": url
            }
        
        elif operation == "send":
            if not client.connected:
                await client.connect()
            
            success = await client.send(message, message_type)
            return {
                "success": success,
                "sent": success
            }
        
        elif operation == "receive":
            if not client.connected:
                await client.connect()
            
            received = await client.receive(timeout)
            
            if received:
                return {
                    "success": True,
                    "type": received.type,
                    "content": received.content,
                    "timestamp": received.timestamp
                }
            else:
                return {
                    "success": False,
                    "message": "No message received or connection closed"
                }
        
        elif operation == "send_receive":
            if not client.connected:
                await client.connect()
            
            sent = await client.send(message, message_type)
            
            if sent:
                received = await client.receive(timeout)
                
                if received:
                    return {
                        "success": True,
                        "sent": True,
                        "received": {
                            "type": received.type,
                            "content": received.content,
                            "timestamp": received.timestamp
                        }
                    }
                else:
                    return {
                        "success": False,
                        "sent": True,
                        "received": None,
                        "error": "No response received"
                    }
            else:
                return {
                    "success": False,
                    "error": "Failed to send message"
                }
        
        elif operation == "close":
            await client.close()
            return {
                "success": True,
                "closed": True
            }
        
        elif operation == "ping_pong":
            if not client.connected:
                await client.connect()
            
            import time
            start = time.time()
            sent = await client.send("ping", "text")
            
            if sent:
                received = await client.receive(5.0)
                elapsed = time.time() - start
                
                return {
                    "success": received is not None,
                    "latency": elapsed
                }
            
            return {"success": False, "error": "Failed to send ping"}
        
        await client.close()
        return {"success": False, "error": f"Unknown operation: {operation}"}
    
    # Run async function
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(run())
