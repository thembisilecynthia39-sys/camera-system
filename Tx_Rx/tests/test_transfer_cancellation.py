import hashlib
from pathlib import Path

import pytest
import requests

from tx_rx.config import TxRxConfig
from tx_rx.jetson_client.transfer import (
    TransferError,
    acknowledge_result,
    get_ply_metadata,
)
from tx_rx.protocol.models import PlyMetadata


TASK_ID = "task-" + "1" * 64
CAPTURE_ID = "capture_001"


def _config(tmp_path: Path) -> TxRxConfig:
    return TxRxConfig(
        schema_version="1.0",
        staging_root=tmp_path / "staging",
        server_url="http://wsl-host:8000",
        result_root=tmp_path / "results",
        request_timeout_seconds=2,
    )


def _metadata(data: bytes) -> PlyMetadata:
    return PlyMetadata(
        magic="GOBJ",
        version="1.0",
        message_type="ply_result",
        task_id=TASK_ID,
        capture_id=CAPTURE_ID,
        filename="3DGS.ply",
        file_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        chunk_size=len(data),
        chunk_count=1,
        created_at="2026-01-01T00:00:00Z",
    )


def test_metadata_timeout_observes_cancellation_before_retry(tmp_path):
    cancelled = False

    class Session:
        def __init__(self) -> None:
            self.timeouts = []

        def get(self, _url, **kwargs):
            nonlocal cancelled
            self.timeouts.append(kwargs["timeout"])
            cancelled = True
            raise requests.Timeout("slow metadata")

    session = Session()

    with pytest.raises(TransferError, match="cancelled"):
        get_ply_metadata(
            TASK_ID,
            CAPTURE_ID,
            _config(tmp_path),
            session,
            cancel_check=lambda: cancelled,
        )

    assert len(session.timeouts) == 1
    assert session.timeouts[0][0] <= 1.0
    assert session.timeouts[0][1] <= 1.0


def test_ack_timeout_observes_cancellation_before_retry(tmp_path):
    data = b"ply"
    final_path = tmp_path / "3DGS.ply"
    final_path.write_bytes(data)
    cancelled = False

    class Session:
        def __init__(self) -> None:
            self.calls = []

        def post(self, url, **kwargs):
            nonlocal cancelled
            self.calls.append((url, kwargs))
            cancelled = True
            raise requests.Timeout("slow ack")

    session = Session()

    with pytest.raises(TransferError, match="cancelled"):
        acknowledge_result(
            _metadata(data),
            final_path,
            _config(tmp_path),
            session,
            cancel_check=lambda: cancelled,
        )

    assert len(session.calls) == 1
    timeout = session.calls[0][1]["timeout"]
    assert timeout[0] <= 1.0
    assert timeout[1] <= 1.0


def test_ack_request_has_task_idempotency_key(tmp_path):
    data = b"ply"
    final_path = tmp_path / "3DGS.ply"
    final_path.write_bytes(data)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message_type": "result_acknowledged",
                "task_id": TASK_ID,
                "capture_id": CAPTURE_ID,
            }

    class Session:
        def __init__(self) -> None:
            self.headers = None

        def post(self, _url, **kwargs):
            self.headers = kwargs["headers"]
            return Response()

    session = Session()

    ack = acknowledge_result(
        _metadata(data),
        final_path,
        _config(tmp_path),
        session,
    )

    assert ack.message_type == "result_acknowledged"
    assert session.headers == {"Idempotency-Key": TASK_ID}
