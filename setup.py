"""Build a private C ABI library; ctypes does not require Python C headers."""
import os
from pathlib import Path
import shlex
import subprocess
import sys

from setuptools import Extension, find_packages, setup
from setuptools.command.build_ext import build_ext

ROOT = Path(__file__).parent
VENDOR = "vendor/kame"


class NativeBuild(build_ext):
    def get_ext_filename(self, fullname):
        suffix = ".dylib" if sys.platform == "darwin" else ".so"
        return os.path.join(*fullname.split(".")) + suffix

    def build_extension(self, ext):
        if sys.platform not in ("darwin", "linux"):
            raise RuntimeError("Native builds support macOS and Linux. Use Python-only tests on other hosts.")
        include_dirs = [VENDOR, VENDOR + "/linux-gpib"]
        library_dirs, libraries, link_args = [], ["usb-1.0"], []
        if os.getenv("LIBUSB_INCLUDE_DIR"):
            include_dirs += [os.environ["LIBUSB_INCLUDE_DIR"]]
        if os.getenv("LIBUSB_LIBRARY_DIR"):
            library_dirs += [os.environ["LIBUSB_LIBRARY_DIR"]]
        try:
            flags = shlex.split(subprocess.check_output(
                ["pkg-config", "--cflags", "--libs", "libusb-1.0"], text=True))
        except (OSError, subprocess.CalledProcessError):
            flags = []
        for flag in flags:
            if flag.startswith("-I"):
                include_dirs.append(flag[2:])
                # KAME uses <libusb-1.0/libusb.h>; pkg-config often supplies
                # the directory intended for the shorter <libusb.h> include.
                folder = Path(flag[2:])
                if folder.name == "libusb-1.0" and (folder / "libusb.h").is_file():
                    include_dirs.append(str(folder.parent))
            elif flag.startswith("-L"):
                library_dirs.append(flag[2:])
            elif flag.startswith("-l"):
                if flag[2:] not in libraries:
                    libraries.append(flag[2:])
            else:
                link_args.append(flag)
        for prefix in ("/opt/homebrew", "/usr/local", "/opt/local"):
            if Path(prefix, "include/libusb-1.0/libusb.h").exists():
                include_dirs.append(prefix + "/include")
                library_dirs.append(prefix + "/lib")
        if not any(Path(p, "libusb-1.0/libusb.h").exists() for p in include_dirs + ["/usr/include"]):
            raise RuntimeError("libusb headers missing. macOS: brew install libusb pkg-config. "
                               "For a custom prefix set LIBUSB_INCLUDE_DIR to the directory containing libusb-1.0/.")
        objects = self.compiler.compile(
            [VENDOR + "/linux-gpib/ni_usb_gpib.c", VENDOR + "/gpib_stubs.c"],
            output_dir=self.build_temp, include_dirs=include_dirs,
            extra_postargs=["-std=gnu11", "-fPIC", "-pthread", "-Wno-unused-function"])
        objects += self.compiler.compile(
            ["native/driver.cpp"], output_dir=self.build_temp, include_dirs=include_dirs,
            extra_postargs=["-std=gnu++17", "-fPIC", "-pthread"])
        # A custom runtime path is also useful with MacPorts and Homebrew.
        if sys.platform == "darwin":
            link_args += ["-Wl,-rpath," + p for p in library_dirs]
        output = self.get_ext_fullpath(ext.name)
        self.mkpath(str(Path(output).parent))
        self.compiler.link_shared_object(objects, output, libraries=libraries,
                                         library_dirs=library_dirs,
                                         extra_postargs=link_args + ["-pthread"],
                                         target_lang="c++")


setup(name="gpib-macarm", version="0.1.0", packages=find_packages("src"),
      package_dir={"": "src"}, package_data={"gpib_macarm": ["py.typed"]},
      python_requires=">=3.10", license="GPL-2.0-or-later",
      entry_points={"console_scripts": ["gpib-macarm=gpib_macarm.cli:main"]},
      ext_modules=[Extension("gpib_macarm._driver", sources=[
    "native/driver.cpp", VENDOR + "/gpib_stubs.c", VENDOR + "/linux-gpib/ni_usb_gpib.c"
])], cmdclass={"build_ext": NativeBuild})
