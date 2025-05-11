"""
Module for initializing the NATS client as a singleton.
This avoids circular imports between main.py and routes/chat_queue.py
"""
import os
import logging
from ..nats_client import GatewayNATS

# Configure logging for NATS
log = logging.getLogger("gateway.nats")
log.setLevel(logging.DEBUG)

# Initialize NATS client with explicit URL
nats_url = os.environ.get("NATS_URL", "nats://nats:4222")
nats_client = GatewayNATS(nats_url) 