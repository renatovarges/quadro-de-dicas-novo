from __future__ import annotations

from io import BytesIO
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


BROWSER_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/google-chrome-stable"),
    Path("/usr/bin/microsoft-edge"),
]


def resolve_browser_path() -> Path | None:
    for candidate in BROWSER_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def export_html_to_png_bytes(html: str, scale: int = 3) -> bytes:
    browser_path = resolve_browser_path()
    worker_path = Path(__file__).with_name("exporter_worker.py")

    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        html_path = temp_dir_path / "preview_export.html"
        png_path = temp_dir_path / "preview_export.png"
        html_path.write_text(html, encoding="utf-8")

        cmd = [
            sys.executable,
            str(worker_path),
            str(html_path),
            str(png_path),
            str(scale),
            str(browser_path) if browser_path else "",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            details = stderr or stdout or f"Processo terminou com código {result.returncode}."
            raise RuntimeError(details)

        if not png_path.exists():
            raise RuntimeError("O subprocesso terminou sem gerar o arquivo PNG.")

        return png_path.read_bytes()


def combine_pngs_to_pdf_bytes(png_images: list[bytes]) -> bytes:
    if not png_images:
        raise RuntimeError("Nenhuma imagem foi gerada para compor o PDF.")

    try:
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise RuntimeError("O módulo Pillow não está instalado no Python que está rodando a plataforma.") from exc

    converted_images: list[Image.Image] = []
    buffers: list[BytesIO] = []

    try:
        for png_bytes in png_images:
            buffer = BytesIO(png_bytes)
            buffers.append(buffer)
            image = Image.open(buffer)
            if image.mode != "RGB":
                image = image.convert("RGB")
            converted_images.append(image)

        output = BytesIO()
        first, *rest = converted_images
        first.save(output, format="PDF", save_all=True, append_images=rest, resolution=300.0)
        return output.getvalue()
    finally:
        for image in converted_images:
            try:
                image.close()
            except Exception:
                pass
        for buffer in buffers:
            buffer.close()
