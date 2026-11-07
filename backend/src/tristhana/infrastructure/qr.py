"""`QrCodes` with segno (ID-04, spec §6): pure Python, imported on the first QR, not at
startup. One small code takes a few milliseconds, so it stays on the event loop."""

import io


class SegnoQrCodes:
    def png(self, url: str) -> bytes:
        import segno

        out = io.BytesIO()
        segno.make(url, error="m").save(out, kind="png", scale=8, border=2)
        return out.getvalue()
