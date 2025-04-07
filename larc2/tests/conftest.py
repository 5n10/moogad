import pytest
import asyncio
import sys
import os
import logging
import pytest_asyncio
from server.websocket_server import WebSocketServer

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest_asyncio.fixture
async def server():
    """Create and initialize a WebSocketServer instance."""
    server_instance = WebSocketServer(port=8766)
    try:
        await server_instance.start()
        yield server_instance
    finally:
        await asyncio.shield(server_instance.stop())

@pytest.fixture(autouse=True)
def configure_logging():
    """Configure logging for tests."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
