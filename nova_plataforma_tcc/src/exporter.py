from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


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


@dataclass
class PngExport:
    png: bytes
    scale: float
    requested_scale: float
    width: int
    height: int
    broken_images: list[str]

    @property
    def scale_reduced(self) -> bool:
        return self.scale + 0.01 < self.requested_scale


def export_htmls_to_png(htmls: list[str], scale: float = 4) -> list[PngExport]:
    """Renderiza várias artes em UMA sessão do navegador (mais rápido e estável que uma por vez)."""
    if not htmls:
        return []
    browser_path = resolve_browser_path()
    worker_path = Path(__file__).with_name("exporter_worker.py")

    with TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        jobs = []
        for index, html in enumerate(htmls):
            html_path = temp_dir_path / f"arte_{index}.html"
            html_path.write_text(html, encoding="utf-8")
            jobs.append({"html": str(html_path), "png": str(temp_dir_path / f"arte_{index}.png")})
        manifest_path = temp_dir_path / "manifest.json"
        result_path = temp_dir_path / "resultado.json"
        manifest_path.write_text(json.dumps({"scale": scale, "jobs": jobs}), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(worker_path), str(manifest_path), str(result_path), str(browser_path or "")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180 + 120 * len(htmls),
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            raise RuntimeError(stderr or stdout or f"Processo terminou com código {result.returncode}.")
        if not result_path.exists():
            raise RuntimeError("O subprocesso terminou sem gerar os arquivos PNG.")

        infos = json.loads(result_path.read_text(encoding="utf-8"))
        return [
            PngExport(
                png=Path(job["png"]).read_bytes(),
                scale=info["scale"],
                requested_scale=info["requested_scale"],
                width=info["width"],
                height=info["height"],
                broken_images=info["broken_images"],
            )
            for job, info in zip(jobs, infos)
        ]


def export_html_to_png_bytes(html: str, scale: float = 3) -> bytes:
    return export_htmls_to_png([html], scale)[0].png


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


def combine_files_to_zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for file_name, file_bytes in files:
            archive.writestr(file_name, file_bytes)
    return output.getvalue()
