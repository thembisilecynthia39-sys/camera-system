"""Bounded streaming parser for the existing requests multipart upload."""

from __future__ import annotations

from email.message import Message
from email.parser import BytesHeaderParser
from pathlib import Path
from typing import BinaryIO, Dict, Optional, Tuple


class MultipartError(Exception):
    """The HTTP multipart body is invalid or exceeds configured limits."""


class _BoundedReader:
    def __init__(self, stream: BinaryIO, length: int) -> None:
        self.stream = stream
        self.remaining = length
        self.buffer = bytearray()

    def read(self, size: int) -> bytes:
        if size <= 0:
            return b""
        output = bytearray()
        if self.buffer:
            take = min(size, len(self.buffer))
            output.extend(self.buffer[:take])
            del self.buffer[:take]
            size -= take
        if size and self.remaining:
            chunk = self.stream.read(min(size, self.remaining))
            if not chunk:
                raise MultipartError("multipart body ended before Content-Length")
            self.remaining -= len(chunk)
            output.extend(chunk)
        return bytes(output)

    def readline(self, maximum: int = 64 * 1024) -> bytes:
        while True:
            index = self.buffer.find(b"\n")
            if index >= 0:
                if index + 1 > maximum:
                    raise MultipartError("multipart line is too long")
                output = bytes(self.buffer[: index + 1])
                del self.buffer[: index + 1]
                return output
            if len(self.buffer) >= maximum:
                raise MultipartError("multipart line is too long")
            if self.remaining <= 0:
                output = bytes(self.buffer)
                self.buffer.clear()
                return output
            chunk = self.stream.read(min(4096, self.remaining))
            if not chunk:
                raise MultipartError("multipart body ended before Content-Length")
            self.remaining -= len(chunk)
            self.buffer.extend(chunk)

    def push_front(self, data: bytes) -> None:
        if data:
            self.buffer[:0] = data


def parse_multipart_upload(
    stream: BinaryIO,
    content_type: str,
    content_length: int,
    output_path: Path,
    maximum_body_size: int,
) -> Tuple[str, Path]:
    if content_length <= 0 or content_length > maximum_body_size:
        raise MultipartError("multipart Content-Length exceeds configured maximum")
    boundary = _multipart_boundary(content_type)
    reader = _BoundedReader(stream, content_length)
    if reader.readline() != b"--" + boundary + b"\r\n":
        raise MultipartError("multipart opening boundary is invalid")

    checksum: Optional[str] = None
    file_seen = False
    final = False
    while not final:
        headers = _read_headers(reader)
        name, filename = _content_disposition(headers)
        if name == "file":
            if file_seen or not filename:
                raise MultipartError("multipart must contain exactly one named file")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("wb") as output:
                final = _copy_part(reader, boundary, output)
            file_seen = True
        elif name == "checksum":
            collector = _LimitedCollector(1024)
            final = _copy_part(reader, boundary, collector)
            try:
                checksum = collector.value.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise MultipartError("checksum is not ASCII") from exc
        else:
            raise MultipartError(f"unexpected multipart field: {name!r}")

    if not file_seen or checksum is None:
        raise MultipartError("multipart requires file and checksum fields")
    if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
        raise MultipartError("checksum must be 64 lowercase hexadecimal characters")
    return checksum, output_path


def _multipart_boundary(content_type: str) -> bytes:
    message = Message()
    message["content-type"] = content_type
    if message.get_content_type() != "multipart/form-data":
        raise MultipartError("Content-Type must be multipart/form-data")
    boundary = message.get_param("boundary", header="content-type")
    if not boundary or len(boundary) > 200:
        raise MultipartError("multipart boundary is missing or too long")
    try:
        return boundary.encode("ascii")
    except UnicodeEncodeError as exc:
        raise MultipartError("multipart boundary must be ASCII") from exc


def _read_headers(reader: _BoundedReader) -> Dict[str, str]:
    lines = bytearray()
    while True:
        line = reader.readline()
        if line == b"\r\n":
            break
        if not line:
            raise MultipartError("multipart headers are incomplete")
        lines.extend(line)
        if len(lines) > 64 * 1024:
            raise MultipartError("multipart headers are too large")
    parsed = BytesHeaderParser().parsebytes(bytes(lines))
    return {key.lower(): value for key, value in parsed.items()}


def _content_disposition(headers: Dict[str, str]) -> Tuple[str, Optional[str]]:
    value = headers.get("content-disposition", "")
    message = Message()
    message["content-disposition"] = value
    if message.get_content_disposition() != "form-data":
        raise MultipartError("part Content-Disposition must be form-data")
    name = message.get_param("name", header="content-disposition")
    filename = message.get_filename()
    if not name:
        raise MultipartError("multipart part name is missing")
    return name, filename


def _copy_part(reader: _BoundedReader, boundary: bytes, output: BinaryIO) -> bool:
    marker = b"\r\n--" + boundary
    retained = b""
    while True:
        chunk = reader.read(64 * 1024)
        if not chunk:
            raise MultipartError("multipart closing boundary is missing")
        data = retained + chunk
        index = data.find(marker)
        if index >= 0:
            output.write(data[:index])
            reader.push_front(data[index + len(marker) :])
            ending = reader.read(2)
            if ending == b"--":
                trailer = reader.readline()
                if trailer not in {b"", b"\r\n"}:
                    raise MultipartError("multipart final boundary trailer is invalid")
                return True
            if ending != b"\r\n":
                raise MultipartError("multipart boundary separator is invalid")
            return False
        keep = min(len(marker) - 1, len(data))
        if len(data) > keep:
            output.write(data[:-keep])
        retained = data[-keep:]


class _LimitedCollector:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.value = b""

    def write(self, data: bytes) -> int:
        if len(self.value) + len(data) > self.maximum:
            raise MultipartError("multipart text field is too large")
        self.value += data
        return len(data)
