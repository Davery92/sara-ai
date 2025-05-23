"""
A mock NATS client implementation that provides a fallback when NATS is unavailable.
This allows the gateway to start and provide basic services without a functional NATS connection.
"""
import asyncio
import json
import logging
import uuid
from typing import Callable, Any, Dict, Optional

log = logging.getLogger("gateway.nats.mock")

class MockNATS:
    """Mock NATS client with minimal implementation to not crash the gateway"""
    def __init__(self):
        self.is_connected = True
        self.subscriptions = {}
        log.info("Created mock NATS client")
        
    async def connect(self, *args, **kwargs):
        """Pretend to connect successfully"""
        log.info("Mock NATS connect called with args: %s, kwargs: %s", args, kwargs)
        return None
        
    async def publish(self, subject: str, payload: bytes, **kwargs):
        """Log the publish but don't actually send anything"""
        log.info("Mock NATS publish - subject: %s, payload: %s, kwargs: %s", 
                subject, payload[:50] if isinstance(payload, bytes) else payload, kwargs)
        return None
        
    async def subscribe(self, subject: str, cb: Callable, **kwargs):
        """Register a subscription callback but never call it"""
        sub_id = str(uuid.uuid4())
        self.subscriptions[sub_id] = (subject, cb)
        log.info("Mock NATS subscribe - subject: %s, kwargs: %s, sub_id: %s", 
                subject, kwargs, sub_id)
        return sub_id
        
    async def unsubscribe(self, sub_id: str):
        """Remove a subscription if it exists"""
        if sub_id in self.subscriptions:
            del self.subscriptions[sub_id]
            log.info("Mock NATS unsubscribe - sub_id: %s", sub_id)
        else:
            log.warning("Mock NATS unsubscribe - sub_id not found: %s", sub_id)
        return None
        
    async def drain(self):
        """Pretend to drain the connection"""
        log.info("Mock NATS drain called")
        return None
        
    async def close(self):
        """Pretend to close the connection"""
        self.is_connected = False
        log.info("Mock NATS close called")
        return None

class GatewayNATSFallback:
    """A fallback implementation of the GatewayNATS class that uses MockNATS"""
    def __init__(self, url: str):
        self.url = url
        self.nc = MockNATS()
        self.connected = True
        self.fallback_mode = True
        log.info("Created GatewayNATS fallback implementation for %s", url)
        
    async def start(self, max_retries: int = 5, delay: float = 2.0):
        """
        Pretend to connect but actually just log the attempt
        and immediately return success
        """
        log.info("Fallback NATS start called for %s", self.url)
        return None
        
    async def stream_request(self, req_subject: str, payload: dict, ws):
        """
        Handle a streaming request in fallback mode by sending
        an error message to the client
        """
        error_msg = {
            "error": "Chat service unavailable (NATS connection error)",
            "status": "service_unavailable",
            "details": "The chat service is temporarily unavailable. Please try again later."
        }
        try:
            log.info("Fallback mode - returning error for chat request")
            await ws.send_text(json.dumps(error_msg))
        except Exception as e:
            log.error("Error sending fallback message: %s", e)
        return None
        
    def is_available(self):
        """Always return False in fallback mode"""
        return False 