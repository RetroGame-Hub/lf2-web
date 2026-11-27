"""Refresh the IPv4 menu in the previously released Android test APK."""
import hashlib
import struct
import sys
from pathlib import Path
from zipfile import ZipFile


ANDROID_SHA256 = "f3f74f7151cde68cac0eb66780647cbd8c93e602df99026ec0d1e19f945f9385"
IOS_SHA256 = "c23301f67b233779afbc310a28f5ac1a2516a6b490af8d7844f22ece270f0cae"
ANDROID_SCRIPTS = "assets/scripts/"
IOS_SCRIPTS = "Payload/openlf2.app/scripts/"
MENU = "base/ui/network.lua"
MANIFEST = "AndroidManifest.xml"
V1_SIGNATURE = {"META-INF/MANIFEST.MF", "META-INF/CERT.SF", "META-INF/CERT.RSA"}


def verify_sha256(path, expected):
    with open(path, "rb") as payload:
        if hashlib.file_digest(payload, "sha256").hexdigest() != expected:
            raise ValueError(f"Unexpected SHA-256 for {path}")


def increment_version(manifest):
    xml_type, offset, end = struct.unpack_from("<HHI", manifest)
    assert xml_type == 3 and end == len(manifest)
    resource_ids = ()
    while offset < end:
        kind, header_size, size = struct.unpack_from("<HHI", manifest, offset)
        assert 8 <= header_size <= size <= end - offset
        data = offset + header_size
        if kind == 0x0180:  # Resource ID map for the indexed XML attribute names.
            resource_ids = tuple(item[0] for item in struct.iter_unpack("<I", manifest[data:offset + size]))
        if kind == 0x0102:  # First element is the manifest root.
            first_attribute, width, count = struct.unpack_from("<HHH", manifest, data + 8)
            for index in range(count):
                position = data + first_attribute + index * width
                _, name, raw, value_size, _, value_type, value = struct.unpack_from("<IIIHBBI", manifest, position)
                if name < len(resource_ids) and resource_ids[name] == 0x0101021B:  # android:versionCode
                    assert (raw, value_size, value_type, value) == (0xFFFFFFFF, 8, 0x10, 11)
                    updated = bytearray(manifest)
                    struct.pack_into("<I", updated, position + 16, 12)
                    return bytes(updated)
            break
        offset += size
    raise ValueError("Android manifest versionCode was not found")


def script_paths(archive, prefix):
    return {entry.filename.removeprefix(prefix) for entry in archive.infolist()
            if entry.filename.startswith(prefix) and not entry.is_dir()}


def repack(android, ios, output):
    verify_sha256(android, ANDROID_SHA256)
    verify_sha256(ios, IOS_SHA256)
    with ZipFile(android) as previous, ZipFile(ios) as reference:
        paths = script_paths(previous, ANDROID_SCRIPTS)
        assert paths == script_paths(reference, IOS_SCRIPTS)
        differences = {path for path in paths
                       if previous.read(ANDROID_SCRIPTS + path) != reference.read(IOS_SCRIPTS + path)}
        assert differences == {MENU}, differences
        assert V1_SIGNATURE <= set(previous.namelist())
        edits = {
            ANDROID_SCRIPTS + MENU: reference.read(IOS_SCRIPTS + MENU),
            MANIFEST: increment_version(previous.read(MANIFEST)),
        }
        with ZipFile(output, "w") as updated:
            for entry in previous.infolist():
                if entry.filename not in V1_SIGNATURE:
                    content = edits[entry.filename] if entry.filename in edits else previous.read(entry)
                    updated.writestr(entry, content)


def verify_output(android, ios, apk):
    with ZipFile(android) as previous, ZipFile(ios) as reference, ZipFile(apk) as updated:
        assert updated.testzip() is None
        assert set(previous.namelist()) - V1_SIGNATURE == set(updated.namelist()) - V1_SIGNATURE
        changed = {name for name in previous.namelist() if name not in V1_SIGNATURE
                   and previous.read(name) != updated.read(name)}
        assert changed == {ANDROID_SCRIPTS + MENU, MANIFEST}, changed
        paths = script_paths(updated, ANDROID_SCRIPTS)
        assert paths == script_paths(reference, IOS_SCRIPTS)
        for name in paths:
            assert updated.read(ANDROID_SCRIPTS + name) == reference.read(IOS_SCRIPTS + name), name


if __name__ == "__main__":
    phase, android, ios, output = sys.argv[1:]
    {"package": repack, "verify": verify_output}[phase](Path(android), Path(ios), Path(output))
