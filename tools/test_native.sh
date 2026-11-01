#!/usr/bin/env bash
# Offline native checks. libusb headers/runtime required; no USB device is opened.
set -eu
cd "$(dirname "$0")/.."
cc_bin="${CC:-cc}"
cxx_bin="${CXX:-c++}"
incs=(-Ivendor/kame -Ivendor/kame/linux-gpib)
links=(-lusb-1.0 -pthread)
if command -v pkg-config >/dev/null 2>&1; then
    read -r -a pkg_flags <<< "$(pkg-config --cflags --libs libusb-1.0)"
    links+=("${pkg_flags[@]}")
fi
if [[ -n "${LIBUSB_INCLUDE_DIR:-}" ]]; then incs+=("-I${LIBUSB_INCLUDE_DIR}"); fi
if [[ -n "${LIBUSB_LIBRARY_DIR:-}" ]]; then links+=("-L${LIBUSB_LIBRARY_DIR}"); fi
if [[ -d /opt/homebrew/include/libusb-1.0 ]]; then incs+=(-I/opt/homebrew/include); links+=(-L/opt/homebrew/lib); fi
if [[ -d /opt/local/include/libusb-1.0 ]]; then incs+=(-I/opt/local/include); links+=(-L/opt/local/lib); fi
mkdir -p build/native-tests
flags=(-std=gnu11 -O1 -g -pthread -fsanitize=address,undefined -fno-omit-frame-pointer)
"$cc_bin" "${flags[@]}" "${incs[@]}" tests/test_compat.c "${links[@]}" -o build/native-tests/test_compat
build/native-tests/test_compat
"$cc_bin" "${flags[@]}" "${incs[@]}" -c vendor/kame/linux-gpib/ni_usb_gpib.c -o build/native-tests/ni_usb_gpib.o
"$cc_bin" "${flags[@]}" "${incs[@]}" -c vendor/kame/gpib_stubs.c -o build/native-tests/gpib_stubs.o
objects=(build/native-tests/ni_usb_gpib.o build/native-tests/gpib_stubs.o)
"$cc_bin" "${flags[@]}" "${incs[@]}" tests/test_parser.c "${objects[@]}" \
    "${links[@]}" -o build/native-tests/test_parser
build/native-tests/test_parser
"$cxx_bin" -std=gnu++17 "${flags[@]:1}" "${incs[@]}" tests/test_driver.cpp "${objects[@]}" \
    "${links[@]}" -o build/native-tests/test_driver
build/native-tests/test_driver
