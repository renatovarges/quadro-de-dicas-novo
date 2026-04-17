from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 5:
        print("Uso: exporter_worker.py <html_path> <png_path> <scale> <browser_path>", file=sys.stderr)
        return 2

    html_path = Path(sys.argv[1])
    png_path = Path(sys.argv[2])
    scale = int(sys.argv[3])
    browser_path = sys.argv[4].strip()

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        print(f"O módulo 'playwright' não está instalado: {exc}", file=sys.stderr)
        return 3

    html = html_path.read_text(encoding="utf-8")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=browser_path or None,
                headless=True,
                args=[
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--font-render-hinting=medium",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1240, "height": 2400},
                device_scale_factor=scale,
                color_scheme="light",
            )
            page = context.new_page()

            try:
                page.set_content(html, wait_until="load", timeout=120000)
                page.wait_for_timeout(1000)
                page.wait_for_function(
                    """
                    async () => {
                        if (document.fonts && document.fonts.ready) {
                            try {
                                await document.fonts.ready;
                            } catch (e) {}
                        }
                        const images = Array.from(document.images || []);
                        await Promise.all(
                            images.map((img) => {
                                if (img.complete) {
                                    return Promise.resolve();
                                }
                                return new Promise((resolve) => {
                                    const done = () => resolve(true);
                                    img.addEventListener('load', done, { once: true });
                                    img.addEventListener('error', done, { once: true });
                                    setTimeout(done, 12000);
                                });
                            })
                        );
                        return true;
                    }
                    """,
                    timeout=120000,
                )
                page.wait_for_timeout(600)
                locator = page.locator("#capture")
                locator.wait_for(state="visible", timeout=30000)

                try:
                    locator.screenshot(path=str(png_path), type="png")
                except Exception:
                    page.screenshot(path=str(png_path), type="png", full_page=True)
            finally:
                context.close()
                browser.close()
    except PlaywrightTimeoutError:
        print("Tempo esgotado ao preparar a arte para exportação.", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 5

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
