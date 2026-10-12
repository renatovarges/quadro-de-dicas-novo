from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# O Chromium falha (imagem cortada/deformada, sem dar erro) acima de ~16384 px em um lado.
MAX_SIDE_PX = 15000
MAX_TOTAL_PIXELS = 140_000_000

WAIT_FOR_ASSETS_JS = """
async () => {
    if (document.fonts && document.fonts.ready) {
        try { await document.fonts.ready; } catch (e) {}
    }
    const images = Array.from(document.images || []);
    await Promise.all(images.map((img) => {
        const settle = () => (img.decode ? img.decode().catch(() => null) : null);
        if (img.complete) return settle();
        return new Promise((resolve) => {
            const done = () => resolve(settle());
            img.addEventListener('load', done, { once: true });
            img.addEventListener('error', done, { once: true });
            setTimeout(done, 15000);
        });
    }));
    return true;
}
"""

BROKEN_IMAGES_JS = """
() => Array.from(document.images || [])
    .filter((img) => !img.complete || img.naturalWidth === 0)
    .map((img) => (img.getAttribute('src') || '').slice(0, 80))
"""


def effective_scale(requested: float, width: float, height: float) -> float:
    longest = max(width, height, 1)
    limit = min(
        requested,
        MAX_SIDE_PX / longest,
        math.sqrt(MAX_TOTAL_PIXELS / max(width * height, 1)),
    )
    return max(1.0, math.floor(limit * 10) / 10)


def png_size(png_path: Path) -> tuple[int, int]:
    header = png_path.read_bytes()[:24]
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def load_page(page, html: str) -> list[str]:
    """Carrega o HTML e espera fontes e imagens; devolve as imagens que não carregaram."""
    broken: list[str] = []
    for attempt in range(3):
        if attempt:
            page.wait_for_timeout(1500)
        page.set_content(html, wait_until="load", timeout=120000)
        page.evaluate(WAIT_FOR_ASSETS_JS)
        broken = page.evaluate(BROKEN_IMAGES_JS)
        if not broken:
            break
    page.wait_for_timeout(400)
    return broken


def render_job(browser, html: str, png_path: Path, requested_scale: float) -> dict:
    # Passo 1: mede a arte (o layout não depende da escala).
    probe_context = browser.new_context(viewport={"width": 1240, "height": 1600}, device_scale_factor=1)
    try:
        probe_page = probe_context.new_page()
        load_page(probe_page, html)
        box = probe_page.locator("#capture").bounding_box()
    finally:
        probe_context.close()
    if not box:
        raise RuntimeError("Não encontrei o elemento #capture na arte.")

    width, height = math.ceil(box["width"]), math.ceil(box["height"])
    scale = effective_scale(requested_scale, width, height)

    # Passo 2: tira o print com a viewport exatamente do tamanho da arte (sem rolagem/costura).
    last_error = ""
    while scale >= 1.0:
        context = browser.new_context(
            viewport={"width": width + 160, "height": height + 40},
            device_scale_factor=scale,
            color_scheme="light",
        )
        try:
            page = context.new_page()
            broken = load_page(page, html)
            locator = page.locator("#capture")
            locator.wait_for(state="visible", timeout=30000)
            locator.screenshot(path=str(png_path), type="png", animations="disabled")
        finally:
            context.close()

        out_w, out_h = png_size(png_path)
        expected_w, expected_h = round(width * scale), round(height * scale)
        if abs(out_w - expected_w) <= 2 and abs(out_h - expected_h) <= 2:
            return {
                "scale": scale,
                "requested_scale": requested_scale,
                "width": out_w,
                "height": out_h,
                "broken_images": broken,
            }
        last_error = f"PNG saiu com {out_w}x{out_h}px, esperado {expected_w}x{expected_h}px em {scale}x."
        scale = math.floor((scale - 0.5) * 10) / 10

    raise RuntimeError(last_error or "Não consegui gerar um PNG íntegro.")


def main() -> int:
    if len(sys.argv) != 4:
        print("Uso: exporter_worker.py <manifest.json> <resultado.json> <browser_path>", file=sys.stderr)
        return 2

    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    result_path = Path(sys.argv[2])
    browser_path = sys.argv[3].strip()

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        print(f"O módulo 'playwright' não está instalado: {exc}", file=sys.stderr)
        return 3

    results: list[dict] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=browser_path or None,
                headless=True,
                args=[
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--font-render-hinting=none",
                    "--force-color-profile=srgb",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            try:
                for job in manifest["jobs"]:
                    html = Path(job["html"]).read_text(encoding="utf-8")
                    results.append(render_job(browser, html, Path(job["png"]), float(manifest["scale"])))
            finally:
                browser.close()
    except PlaywrightTimeoutError:
        print("Tempo esgotado ao preparar a arte para exportação.", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 5

    result_path.write_text(json.dumps(results), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
