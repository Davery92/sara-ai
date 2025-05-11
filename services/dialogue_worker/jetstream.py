import os, jwt, asyncio, logging, sys
from nats.aio.client import Client as NATS
from nats.js.api import ConsumerConfig, StreamConfig
from prometheus_client import Counter
from nats.errors import TimeoutError
from jwt.exceptions import InvalidTokenError   

# Configure logging to output to console with timestamp
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("jetstream")

ALG   = os.getenv("JWT_ALG", "HS256")
KEY   = os.getenv("JWT_SECRET", "dev-secret-change-me")
NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")
AUTH_FAILS = Counter("dw_auth_fail_total", "JWT verification failures")
NATS_CONN_RETRIES = Counter("dw_nats_conn_retry_total", "NATS connection retry attempts")

def verify(tok: str):    # raises on bad sig / expiry
    try:
        return jwt.decode(tok, KEY, algorithms=[ALG])
    except jwt.InvalidTokenError:
        AUTH_FAILS.inc()
        raise

async def consume(loop_cb):
    nc = NATS()
    
    logger.info(f"Starting dialogue worker with NATS URL: {NATS_URL}")
    logger.info(f"JWT settings: ALG={ALG}")
    
    # Implement exponential backoff for NATS connection
    delay = 1
    max_delay = 30  # Max delay of 30 seconds
    attempt = 1
    
    while True:
        try:
            logger.info(f"Attempt {attempt}: Connecting to NATS at {NATS_URL}")
            await nc.connect(servers=[NATS_URL])
            logger.info(f"✅ Successfully connected to NATS after {attempt} attempts")
            break  # Connection successful
        except ConnectionRefusedError as e:
            NATS_CONN_RETRIES.inc()
            logger.warning(f"❌ NATS not ready ({e}) - retrying in {delay}s (attempt {attempt})")
        except Exception as e:
            NATS_CONN_RETRIES.inc()
            logger.error(f"❌ Unexpected NATS connection error: {str(e)} - retrying in {delay}s (attempt {attempt})")
            logger.error(f"Error type: {type(e)}")
        
        await asyncio.sleep(delay)
        delay = min(delay * 2, max_delay)  # Exponential backoff with maximum delay
        attempt += 1
    
    try:
        logger.info("Getting JetStream context")
        js = nc.jetstream()
        logger.info("Successfully got JetStream context")

        # idempotently create the CHAT stream if it's missing
        try:
            logger.info("Checking if CHAT stream exists")
            await js.stream_info("CHAT")
            logger.info("CHAT stream exists")
        except Exception as e:
            logger.info(f"Creating CHAT stream: {e}")
            await js.add_stream(StreamConfig(name="CHAT",
                                            subjects=["chat.request.*"],
                                            storage="file",
                                            max_age=72*60*60))
            logger.info("CHAT stream created successfully")

        # durable pull consumer
        try:
            logger.info("Checking if consumer exists")
            await js.consumer_info("CHAT", "dw")
            logger.info("Consumer exists")
        except Exception as e:
            logger.info(f"Creating consumer: {e}")
            await js.add_consumer("CHAT",
                                ConsumerConfig(durable_name="dw",
                                                ack_policy="explicit"))
            logger.info("Consumer created successfully")

        logger.info("Setting up pull subscription")
        sub = await js.pull_subscribe("chat.request.*", "dw")
        logger.info("Pull subscription set up successfully")

        logger.info("Starting main message processing loop")
        while True:
            try:
                msgs = await sub.fetch(10, timeout=1)
            except TimeoutError:
                await asyncio.sleep(0.1)
                continue
            except Exception as e:
                logger.error("Unexpected fetch error: %s", e)
                await asyncio.sleep(1)
                continue

            for m in msgs:
                try:
                    logger.debug("Processing message: %s", m.subject)

                    # ── Auth header → verify JWT ──────────────────────────
                    tok = (m.headers or {}).get("Auth")
                    if tok is None:
                        raise ValueError("Missing Auth header")

                    if isinstance(tok, bytes):
                        tok = tok.decode()

                    verify(tok)                   # raises on bad token

                    # hand off to on_request(); it will ack/term
                    await loop_cb(m, nc)

                except Exception as e:
                    logger.warning("Rejecting message: %s", e)
                    await m.term()

            await asyncio.sleep(0.1)              # light back-off

            # slight backoff to avoid a tight spin
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Fatal error in consume loop: {e}")
        raise
