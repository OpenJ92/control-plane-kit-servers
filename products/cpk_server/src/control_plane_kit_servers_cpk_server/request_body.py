"""Bound owned request accumulation before retaining each incoming chunk."""

from collections.abc import AsyncIterable


MCP_ENVELOPE_MAX_BYTES = 1_048_576


class RequestBodyTooLarge(Exception):
    """Payload-free signal for the process boundary's fixed overflow response."""


async def collect_request_body(chunks: AsyncIterable[bytes], max_bytes: int) -> bytes:
    """Collect an inclusive byte budget without appending or draining overflow."""
    body = bytearray()
    async for chunk in chunks:
        if len(chunk) > max_bytes - len(body):
            raise RequestBodyTooLarge("request body too large")
        body.extend(chunk)
    return bytes(body)
