from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import shutil

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "zcharge-magisk.zip"
STAGE = ROOT / ".zcharge-magisk"

FILES = [
    "module.prop",
    "customize.sh",
    "service.sh",
    "post-fs-data.sh",
    "uninstall.sh",
    "tools.sh",
    "zcharge.db",
    "system",
    "META-INF",
]


def main():
    if not (ROOT / "module.prop").exists():
        raise SystemExit(
            "ERRORE: esegui lo script dalla root del repository zcharge"
        )

    if STAGE.exists():
        shutil.rmtree(STAGE)

    if OUT.exists():
        OUT.unlink()

    STAGE.mkdir()

    for name in FILES:
        src = ROOT / name

        if not src.exists():
            print(f"[skip] {name}")
            continue

        dst = STAGE / name

        if src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        print(f"[+] {name}")

    with ZipFile(OUT, "w", ZIP_DEFLATED) as z:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(STAGE).as_posix())

    shutil.rmtree(STAGE)

    print()
    print(f"Creato: {OUT}")
    print(f"Dimensione: {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
