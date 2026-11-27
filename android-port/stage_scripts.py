"""Stage the verified iOS friend-room release's shared scripts and game data."""
import argparse
import hashlib
import shutil
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZipFile

RELEASE_SHA256 = "846c2c031814d94f639cdd7051e257055d310b507af5f53335885be3bf9a3839"
SCRIPT_PREFIX = "Payload/openlf2.app/scripts/"
REQUIRED = {
    "base/game/network.lua",
    "base/ui/network.lua",
    "base/ui/touch_gamepad.lua",
    "data-override/data/stage.dat",
    "runtime/bootstrap.lua",
}


def stage(ipa: Path, engine: Path):
    with ipa.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != RELEASE_SHA256:
            raise ValueError("The source IPA does not match the pinned friend-room release")
    scripts = engine / "scripts"
    if not (scripts / "runtime/bootstrap.lua").is_file():
        raise ValueError("The destination must be a prepared OpenLF2 source checkout")

    with ZipFile(ipa) as release, TemporaryDirectory(dir=engine) as temp:
        imported = Path(temp) / "scripts"
        names = set()
        for member in release.infolist():
            if member.is_dir() or not member.filename.startswith(SCRIPT_PREFIX):
                continue
            path = PurePosixPath(member.filename.removeprefix(SCRIPT_PREFIX))
            if path.is_absolute() or ".." in path.parts or path.as_posix() in names:
                raise ValueError(f"Invalid script path: {member.filename}")
            names.add(path.as_posix())
            destination = imported / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            with release.open(member) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
        if not REQUIRED.issubset(names):
            raise ValueError(f"The source IPA is missing: {sorted(REQUIRED - names)}")
        scripts.rename(Path(temp) / "previous-scripts")
        try:
            imported.rename(scripts)
        except OSError:
            (Path(temp) / "previous-scripts").rename(scripts)
            raise

    print(f"Staged {len(names)} shared files from the verified iOS release")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ipa", type=Path)
    parser.add_argument("engine", type=Path)
    options = parser.parse_args()
    stage(options.ipa, options.engine.resolve())
