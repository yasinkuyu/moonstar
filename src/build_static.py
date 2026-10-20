#! /usr/bin/python3

# build_static.py
#
# Builds the web UI as a static site for GitHub Pages (output: site/).
# Dictionary lists are written as JSON with the same loaders and handlers as
# ui.py; the spell checker runs the Python engine in the browser (Pyodide),
# see src/static/api.js.
#
# Requires data/ and output/MTU.TUR.TXT (run mtu_tur.py first).
#
#     python3 src/build_static.py [output_dir]
#     python3 src/build_static.py --publish     # build site/ and push it as the gh-pages branch
#
# @yasinkuyu

import json
import os
import shutil
import subprocess
import sys
import tempfile

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

import ui
from core.constants import DGROUP_FILE_OFFSET, project_path
from engine.tur_lexicon import _MUTATION_TABLE_DS

ASSETS = ["MoonStar.svg", "buttons_sprite.png", "gallows_sprite.png", "keys_sprite.png", "logo_acer.png",
          "moonstar.ico", "moonstar_banner.png", "moonstar_icon.png"]
# Python sources the spell checker needs (engine/__init__ imports every engine module)
PY_SOURCES = ["spell_check.py", "core", "engine"]


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def page_html():
    html = ui.HTML_PAGE.replace("/assets/", "assets/")
    shim = '<script src="api.js"></script>\n'
    head = html.index("<head>") + len("<head>")
    return html[:head] + "\n" + shim + html[head:]


def copy_python(out_dir):
    """Engine sources + MTU.TUR / MTU.SOZ / KONTROL.SOZ, and an MTU.EXE stand-in that holds only the
    256-byte final-letter mutation table (ds:0x1588), the only EXE bytes the speller reads."""
    manifest = []
    py_dir = os.path.join(out_dir, "py")
    for item in PY_SOURCES:
        src = os.path.join(script_dir, item)
        files = [src] if os.path.isfile(src) else [
            os.path.join(src, n) for n in sorted(os.listdir(src)) if n.endswith(".py")]
        for f in files:
            rel = os.path.join("src", os.path.relpath(f, script_dir))
            os.makedirs(os.path.dirname(os.path.join(py_dir, rel)), exist_ok=True)
            shutil.copy(f, os.path.join(py_dir, rel))
            manifest.append(rel)

    os.makedirs(os.path.join(py_dir, "data"), exist_ok=True)
    for name in ("MTU.TUR", "MTU.SOZ", "KONTROL.SOZ"):
        shutil.copy(project_path("data", name), os.path.join(py_dir, "data", name))
        manifest.append("data/" + name)

    with open(project_path("data", "MTU.EXE"), "rb") as f:
        exe = f.read()
    start = DGROUP_FILE_OFFSET + _MUTATION_TABLE_DS
    with open(os.path.join(py_dir, "data", "MTU.EXE"), "wb") as f:
        f.write(bytes(start) + exe[start:start + 256])
    manifest.append("data/MTU.EXE")

    write_json(os.path.join(py_dir, "manifest.json"), manifest)


def publish(out_dir):
    """Pushes out_dir as the single commit of the gh-pages branch of the origin remote."""
    git = lambda *args, cwd=None: subprocess.run(["git", *args], cwd=cwd, check=True,
                                                 capture_output=True, text=True).stdout.strip()
    root = project_path()
    remote = git("remote", "get-url", "origin", cwd=root)
    name, email = git("config", "user.name", cwd=root), git("config", "user.email", cwd=root)
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(out_dir, tmp, dirs_exist_ok=True)
        git("init", "-q", "-b", "gh-pages", cwd=tmp)
        git("add", "-A", cwd=tmp)
        git("-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-q", "-m", "Deploy web UI", cwd=tmp)
        git("push", "-q", "--force", remote, "gh-pages", cwd=tmp)
    print(f"Published to the gh-pages branch of {remote}")


def main():
    args = [a for a in sys.argv[1:] if a != "--publish"]
    out_dir = os.path.abspath(args[0] if args else project_path("site"))
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(os.path.join(out_dir, "api"))
    os.makedirs(os.path.join(out_dir, "assets"))

    handler = ui.MoonStarHandler.__new__(ui.MoonStarHandler)  # only its pure helper methods are used
    api = os.path.join(out_dir, "api")
    write_json(os.path.join(api, "stats.json"), handler.get_stats())
    write_json(os.path.join(api, "trk.json"), ui.TRK_DATA)
    write_json(os.path.join(api, "tur.json"), ui.TUR_DATA)
    write_json(os.path.join(api, "syn.json"), ui.SYN_DATA)
    write_json(os.path.join(api, "rev.json"), ui.REV_DATA)
    write_json(os.path.join(api, "quiz.json"), ui.QUIZ_DATA)
    write_json(os.path.join(api, "help.json"), ui.HELP_DATA)
    write_json(os.path.join(api, "game.json"), ui.GAME_WORDS)
    with open(project_path("data", "TEST"), "r", encoding="cp857", errors="replace") as f:
        write_json(os.path.join(api, "demo.json"), {"content": f.read(), "filename": "TEST"})

    for name in ASSETS:
        shutil.copy(project_path("assets", name), os.path.join(out_dir, "assets", name))
    shutil.copytree(project_path("assets", "exe"), os.path.join(out_dir, "assets", "exe"))  # EXE dialog bitmaps
    shutil.copy(os.path.join(script_dir, "static", "api.js"), os.path.join(out_dir, "api.js"))
    copy_python(out_dir)

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page_html())
    open(os.path.join(out_dir, ".nojekyll"), "w").close()  # serve files as they are

    size = sum(os.path.getsize(os.path.join(d, n)) for d, _, ns in os.walk(out_dir) for n in ns)
    print(f"Static site written to {out_dir} ({size / 1e6:.1f} MB)")
    if "--publish" in sys.argv[1:]:
        publish(out_dir)


if __name__ == "__main__":
    main()
