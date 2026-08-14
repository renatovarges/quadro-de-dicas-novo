from pathlib import Path
import runpy
import sys


APP_FILE = Path(__file__).resolve().parent / "nova_plataforma_tcc" / "app.py"
for module_name in list(sys.modules):
    if module_name == "src" or module_name.startswith("src."):
        del sys.modules[module_name]
runpy.run_path(str(APP_FILE), run_name="__main__")
