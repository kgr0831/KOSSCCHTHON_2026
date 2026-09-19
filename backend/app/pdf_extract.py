"""Bounded PDF helper. Private bytes/text only travel over captured pipes."""
import io
import json
import sys

from windows_job import WindowsJob

if __name__ == "__main__":
    job = WindowsJob(memory_mb=384)
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(sys.stdin.buffer.read(10 * 1024 * 1024 + 1)))
        if len(reader.pages) > 100:
            raise ValueError()
        chunks, size = [], 0
        for page in reader.pages:
            content = page.get_contents()
            if content and len(content.get_data()) > 8 * 1024 * 1024:
                raise ValueError()
            text = page.extract_text() or ""
            size += len(text)
            if size > 100000:
                raise ValueError()
            chunks.append(text)
        sys.stdout.buffer.write(json.dumps({"text": "\n".join(chunks)}, ensure_ascii=False).encode("utf-8"))
    except Exception:
        raise SystemExit(1) from None
