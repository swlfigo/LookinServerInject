#!/usr/bin/env python3
"""Build a generic iOS dylib, optionally packaged for rootless ElleKit injection."""

import argparse
import gzip
import io
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ID = "com.isylar.lookininject"
INSTALL_DIR = "var/jb/Library/MobileSubstrate/DynamicLibraries"


def bundle_id(value):
    if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value):
        raise argparse.ArgumentTypeError("Bundle ID must contain dot-separated identifiers, without wildcards")
    return value


def ios_version(value):
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", value):
        raise argparse.ArgumentTypeError("Use an iOS version such as 15.0")
    if tuple(int(part) for part in value.split(".")) < (13, 0):
        raise argparse.ArgumentTypeError("The injection notice requires iOS 13.0 or newer")
    return value


def package_version(value):
    if not re.fullmatch(r"[0-9][A-Za-z0-9.+~]*(?:-[A-Za-z0-9.+~]+)?", value):
        raise argparse.ArgumentTypeError("Invalid Debian package version")
    return value


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def tar_gz(files):
    """Create root-owned archives without relying on a local dpkg installation."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        directories = set()
        for name in files:
            directories.update(str(parent) for parent in Path(name).parents if str(parent) != ".")
        for name in sorted(directories, key=lambda path: (path.count("/"), path)):
            info = tarfile.TarInfo("./" + name)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            archive.addfile(info)
        for name, (data, mode) in files.items():
            info = tarfile.TarInfo("./" + name)
            info.size = len(data)
            info.mode = mode
            archive.addfile(info, io.BytesIO(data))
    return gzip.compress(buffer.getvalue(), mtime=0)


def write_deb(path, dylib, filter_data, version, minimum_ios):
    # Standard Debian 2.0 package: an ar archive containing two gzip-compressed tars.
    control = (
        f"Package: {PACKAGE_ID}\n"
        "Name: LookinInject\n"
        f"Version: {version}\n"
        "Architecture: iphoneos-arm64\n"
        "Maintainer: sylar\n"
        "Author: sylar\n"
        "Section: Tweaks\n"
        "Priority: optional\n"
        f"Depends: ellekit, firmware (>= {minimum_ios})\n"
        "Description: Inject LookinServer into the explicitly selected apps for UI inspection.\n"
    ).encode("utf-8")
    members = {
        "debian-binary": b"2.0\n",
        "control.tar.gz": tar_gz({"control": (control, 0o644)}),
        "data.tar.gz": tar_gz({
            f"{INSTALL_DIR}/LookinInject.dylib": (dylib.read_bytes(), 0o755),
            f"{INSTALL_DIR}/LookinInject.plist": (filter_data, 0o644),
        }),
    }
    with path.open("wb") as archive:
        archive.write(b"!<arch>\n")
        for name, data in members.items():
            header = f"{name:<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
            archive.write(header.encode("ascii"))
            archive.write(data)
            if len(data) % 2:
                archive.write(b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-id", action="append", type=bundle_id, default=[],
                        help="Exact target App Bundle ID; repeat for multiple apps. Omit for dylib only.")
    parser.add_argument("--arch", action="append", choices=("arm64", "arm64e"),
                        help="Mach-O architecture; repeat for a fat dylib (default: arm64)")
    parser.add_argument("--min-ios", type=ios_version, default="15.0",
                        help="Deployment target (default: 15.0; rootless packages require >= 15.0)")
    parser.add_argument("--no-notice", action="store_true", help="Disable the injection-success banner")
    parser.add_argument("--package-version", type=package_version, default="0.2.0")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "rootless")
    args = parser.parse_args()
    if args.bundle_id and tuple(int(part) for part in args.min_ios.split(".")) < (15, 0):
        parser.error("Rootless packaging requires --min-ios 15.0 or newer")
    for executable in ("xcrun", "codesign"):
        if not shutil.which(executable):
            parser.error(f"{executable} is required; install Xcode and select it with xcode-select")

    architectures = list(dict.fromkeys(args.arch or ["arm64"]))
    bundles = list(dict.fromkeys(args.bundle_id))
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    sdk = run(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"],
              capture_output=True, text=True).stdout.strip()
    source_root = ROOT / "LookinInject" / "Src"
    sources = [ROOT / "LookinInject" / "EntryPointFile.m"] + sorted(source_root.rglob("*.m"))
    include_dirs = sorted({path.parent for path in source_root.rglob("*.h")})

    # Build into a temporary directory so a failed compile cannot overwrite a working dylib.
    with tempfile.TemporaryDirectory(prefix=".lookin-build-", dir=output) as temporary:
        stage = Path(temporary)
        dylib = stage / "LookinInject.dylib"
        command = ["xcrun", "--sdk", "iphoneos", "clang"]
        for architecture in architectures:
            command.extend(["-arch", architecture])
        command.extend([
            "-isysroot", sdk, f"-miphoneos-version-min={args.min_ios}",
            "-dynamiclib", "-fobjc-arc", "-fblocks", "-O2", "-Wno-deprecated-declarations",
            "-DSHOULD_COMPILE_LOOKIN_SERVER=1",
            f"-DLOOKIN_INJECT_SHOW_NOTICE={int(not args.no_notice)}",
            "-Wl,-install_name,@rpath/LookinInject.dylib",
        ])
        for framework in ("Foundation", "UIKit", "QuartzCore", "CoreGraphics"):
            command.extend(["-framework", framework])
        for directory in include_dirs:
            command.extend(["-I", str(directory)])
        command.extend(str(source) for source in sources)
        command.extend(["-o", str(dylib)])
        print(f"Building {len(sources)} sources for {', '.join(architectures)} (iOS >= {args.min_ios})", flush=True)
        run(command)
        run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(dylib)])
        run(["codesign", "--verify", "--strict", str(dylib)])

        filter_path = stage / "LookinInject.plist"
        deb = stage / "LookinInject.deb"
        if bundles:
            filter_data = plistlib.dumps({"Filter": {"Bundles": bundles}})
            filter_path.write_bytes(filter_data)
            write_deb(deb, dylib, filter_data, args.package_version, args.min_ios)
        metadata = {
            "architectures": architectures,
            "minimumIOS": args.min_ios,
            "showNotice": not args.no_notice,
            "bundleIDs": bundles,
            "packageVersion": args.package_version if bundles else None,
        }
        (stage / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        for name in ("LookinInject.dylib", "build-info.json", "LookinInject.plist", "LookinInject.deb"):
            staged = stage / name
            destination = output / name
            if staged.exists():
                staged.replace(destination)
            elif destination.exists():
                # Remove only this script's known packaging outputs when rebuilding without a target.
                destination.unlink()

    print(f"Dylib: {output / 'LookinInject.dylib'}")
    if bundles:
        print(f"Rootless package: {output / 'LookinInject.deb'}")
        print(f"Injection filter: {', '.join(bundles)}")
    else:
        print("No Bundle ID supplied: built a generic dylib only.")
    print(f"Injection notice: {'disabled' if args.no_notice else 'enabled (iPhone / iPad)'}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        sys.exit(1)
