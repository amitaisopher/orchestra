from __future__ import annotations

import logging
import random
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _iso(ts_ms: int) -> str:
  return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
  """Lambda B3 – Container runtime (Python in image).

  Logs a message and returns execution metadata.
  """
  start_ms = int(time.time() * 1000)
  logger.info("Lambda B3")
  delay = random.randint(1, 10)
  time.sleep(delay)
  end_ms = int(time.time() * 1000)
  return {
    "functionName": getattr(context, "function_name", "unknown"),
    "requestId": getattr(context, "aws_request_id", "unknown"),
    "runtime": "container:python3.12",
    "task": "B3",
    "startTime": _iso(start_ms),
    "endTime": _iso(end_ms),
    "durationMs": end_ms - start_ms,
    "delaySeconds": delay,
  }