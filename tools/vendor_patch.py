"""Reproduce local fixes and record provenance. Run only when refreshing vendor.

python tools/vendor_patch.py --source ../KAME/modules/charinterface/usermode-linux-gpib
The source checkout must be at the commit recorded below. Normal installs never
run this script and do not require the original KAME checkout or network access.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "f451025dc4215c5d85f39b71303f9008ccee66bc"


def replace(text, old, new, count=1):
    assert text.count(old) == count, old[:100]
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    actual = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual != COMMIT:
        raise SystemExit("Unexpected KAME revision: " + actual)
    dest = ROOT / "vendor/kame"
    originals = {}
    # Only files needed by the C driver, plus upstream wrapper for reference.
    files = [p for p in source.rglob("*") if p.is_file() and
             (p.suffix in (".h", ".c") or p.name in ("NiGpibDriver.cpp", "README", "COPYING", "AUTHORS"))]
    for path in files:
        rel = path.relative_to(source)
        originals[str(rel).replace("\\", "/")] = path.read_bytes()
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest / rel)

    p = dest / "osx_compat.h"
    s = p.read_text(encoding="utf-8")
    s = replace(s, "    int                interval;", "    int                interval;\n    unsigned int       timeout_ms; /* gpib-macarm: per-transfer USB timeout */")
    s, n = re.subn(r"volatile int\s+cancelled;", "int cancelled; /* accessed through compiler atomics */", s)
    assert n == 2  # passive timer and URB each have a cancellation flag
    # Use explicit atomics: volatile is not thread synchronization on ARM.
    s = re.sub(r"urb->cancelled\s*=\s*([01]);", r"__atomic_store_n(&urb->cancelled, \1, __ATOMIC_RELEASE);", s)
    s = re.sub(r"(?<!&)urb->cancelled", r"__atomic_load_n(&urb->cancelled, __ATOMIC_ACQUIRE)", s)
    s = replace(s, "            urb->transfer_buffer_length, &actual, 10000);",
                   "            urb->transfer_buffer_length, &actual, urb->timeout_ms);", count=2)
    helper = """
/* gpib-macarm: preserve transport error identity instead of collapsing to EIO. */
static inline int kg_usb_errno(int r) {
    switch (r) {
    case 0: return 0;
    case LIBUSB_ERROR_TIMEOUT: return -ETIMEDOUT;
    case LIBUSB_ERROR_NO_DEVICE: return -ENODEV;
    case LIBUSB_ERROR_ACCESS: return -EACCES;
    case LIBUSB_ERROR_BUSY: return -EBUSY;
    case LIBUSB_ERROR_PIPE: return -EPIPE;
    case LIBUSB_ERROR_OVERFLOW: return -EOVERFLOW;
    default: return -EIO;
    }
}
"""
    s = replace(s, "static void *_urb_thread_func(void *arg) {", helper + "\nstatic void *_urb_thread_func(void *arg) {")
    s = s.replace("(r == 0) ? 0 : -EIO", "kg_usb_errno(r)")
    s = replace(s, "        int r = pthread_create(&urb->thread, NULL, _urb_thread_func, urb);\n        if (r != 0) return -ENOMEM;\n        urb->thread_started = 1;",
                   "        urb->thread_started = 1; /* before child can resubmit */\n        int r = pthread_create(&urb->thread, NULL, _urb_thread_func, urb);\n        if (r != 0) { urb->thread_started = 0; return -ENOMEM; }")
    s = replace(s, "            if (urb->complete) urb->complete(urb);\n            if (__atomic_load_n(&urb->cancelled, __ATOMIC_ACQUIRE)) break;",
                   "            if (urb->complete) urb->complete(urb);\n            if (r == LIBUSB_ERROR_NO_DEVICE) break;\n            if (r != 0) usleep(40000); /* avoid spinning on repeated errors */\n            if (__atomic_load_n(&urb->cancelled, __ATOMIC_ACQUIRE)) break;")
    p.write_text(s, encoding="utf-8", newline="\n")

    p = dest / "linux-gpib/ni_usb_gpib.c"
    s = p.read_text(encoding="utf-8")
    marker = "\t\t&ni_usb_bulk_complete, context);"
    s = replace(s, marker, marker + "\n#ifndef __KERNEL__\n\tni_priv->bulk_urb->timeout_ms = (unsigned int)timeout_msecs;\n#endif", count=2)
    start = s.index("int parse_board_ibrd_readback(")
    end = s.index("int ni_usb_parse_reg_write_status_block(", start)
    bounded = r'''
/* gpib-macarm 2026-10-30: bounds-aware NI IBRD parser. The original parser
 * had no received-length argument and could read beyond a short USB packet. */
int parse_board_ibrd_readback(const uint8_t *raw, int raw_length,
    struct ni_usb_status_block *status, uint8_t *data, int capacity, int *actual)
{
    int i=0, total=0, copied=0, last_block=0, blocks=0, k, compact;
    struct ni_usb_status_block reg;
    if (!raw || !status || !data || !actual || raw_length < 0 || capacity < 0)
        return -EPROTO;
    *actual=0;
    while (i < raw_length && (raw[i] == NIUSB_IBRD_DATA_ID || raw[i] == NIUSB_IBRD_EXTENDED_DATA_ID)) {
        int length=raw[i++] == NIUSB_IBRD_DATA_ID ? 15 : 30;
        if (length == 30) { if (i >= raw_length || raw[i++] != 0) return -EPROTO; }
        if (raw_length-i < length) return -EPROTO;
        for (k=0; k<length; ++k) {
            if (copied < capacity) data[copied++]=raw[i+k];
        }
        i+=length; total+=length; last_block=length; ++blocks;
    }
    /* HS hardware can omit the register-write acknowledgement: accept only
     * status(8), ADR1/last/padding(4), optional register status/count(12), TERM(4). */
    if (raw_length-i != 16 && raw_length-i != 28) return -EPROTO;
    compact = raw_length-i == 16;
    ni_usb_parse_status_block(raw+i,status); i+=8;
    if (status->id != NIUSB_IBRD_STATUS_ID) return -EPROTO;
    ++i; /* ADR1 */
    k=raw[i++];
    /* Observed HS compact replies have an unreliable final-block count on
     * small reads. Derive their size from the requested capacity minus the
     * IBRD residual; require it to fit precisely within the final data block. */
    if (compact) {
        if (status->count > capacity) return -EPROTO;
        *actual=capacity-status->count;
        if ((!blocks && *actual != 0) ||
            (blocks && (*actual <= total-last_block || *actual > total))) return -EPROTO;
    } else {
        if ((!blocks && k != 0) || (blocks && k > last_block)) return -EPROTO;
        *actual=blocks ? total-last_block+k : 0;
    }
    if (*actual > capacity || *actual > copied) return -EPROTO;
    if (raw[i++] || raw[i++]) return -EPROTO;
    if (raw_length-i == 16) {
        ni_usb_parse_status_block(raw+i,&reg); i+=8;
        if (reg.id != NIUSB_REG_WRITE_ID || reg.error_code != NIUSB_NO_ERROR) return -EPROTO;
        if (raw[i++] != 2) return -EPROTO;
        for (k=0;k<3;++k) if (raw[i++]) return -EPROTO;
    }
    if (raw[i++] != NIUSB_TERM_ID) return -EPROTO;
    for (k=0;k<3;++k) if (raw[i++]) return -EPROTO;
    return i;
}

'''
    s = s[:start] + bounded + s[end:]
    s = replace(s, "parse_board_ibrd_readback(in_data, &status, buffer, length, &actual_length)",
                   "parse_board_ibrd_readback(in_data, usb_bytes_read, &status, buffer, length, &actual_length)")
    s = replace(s, "if(actual_length != length - status.count)",
                   "if(status.count > length || actual_length != (int)(length - status.count))")
    s = replace(s, "\t\tni_usb_dump_raw_block(in_data, usb_bytes_read);\n\t}\n\tkfree(in_data);",
                   "\t\tni_usb_dump_raw_block(in_data, usb_bytes_read);\n\t\tkfree(in_data);\n\t\treturn -EPROTO;\n\t}\n\tkfree(in_data);")
    # A short successful USB transfer is still a protocol error.
    pattern = r"(if\(\(retval && retval != -ERESTARTSYS\) \|\| (?:usb_bytes_read|bytes_read) != 12\)\s*\{.*?kfree\(in_data\);\s*)return retval;"
    s, n = re.subn(pattern, r"\1return retval ? retval : -EPROTO;", s, flags=re.S)
    assert n >= 2, n
    # Guard interrupt status parsing before the 8-byte decoder touches it.
    s = replace(s, "\tni_usb_parse_status_block(urb->transfer_buffer, &status);",
                   "\tif (urb->actual_length < 8) return; /* gpib-macarm: truncated interrupt status */\n\tni_usb_parse_status_block(urb->transfer_buffer, &status);")
    # Validate write/command tags and residual counts before unsigned arithmetic.
    a=s.index("static int ni_usb_write("); b=s.index("int ni_usb_command_chunk(",a)
    chunk=s[a:b]
    chunk=replace(chunk,"\tni_usb_parse_status_block(in_data, &status);\n\tkfree(in_data);",
                  "\tni_usb_parse_status_block(in_data, &status);\n\tkfree(in_data);\n\tif (status.id != 0x0d || status.count > length) return -EPROTO;")
    s=s[:a]+chunk+s[b:]
    a=s.index("int ni_usb_command_chunk("); b=s.index("int ni_usb_command(",a)
    chunk=s[a:b]
    chunk=replace(chunk,"\tni_usb_parse_status_block(in_data, &status);\n\tkfree(in_data);",
                  "\tni_usb_parse_status_block(in_data, &status);\n\tkfree(in_data);\n\tif (status.id != 0x0c || status.count > length) return -EPROTO;")
    # Preserve a GPIB timeout error from command packets.
    chunk=replace(chunk,"\tcase NIUSB_NO_BUS_ERROR:","\tcase NIUSB_TIMEOUT_ERROR:\n\t\treturn -ETIMEDOUT;\n\tcase NIUSB_NO_BUS_ERROR:")
    s=s[:a]+chunk+s[b:]
    # Expose checked bus control variants. Original gpib_interface has void APIs.
    s += r'''
/* gpib-macarm: checked controls for the standalone wrapper. */
int kg_ni_remote(gpib_board_t *board, int enabled)
{
    ni_usb_private_t *p=board->private_data;
    struct ni_usb_register reg;
    unsigned int ibsta;
    reg.device=NIUSB_SUBDEV_TNT4882;
    reg.address=nec7210_to_tnt4882_offset(AUXMR);
    reg.value=enabled ? AUX_SREN : AUX_CREN;
    return ni_usb_write_registers(p,&reg,1,&ibsta);
}
int kg_ni_ifc(gpib_board_t *board)
{
    ni_usb_private_t *p=board->private_data;
    uint8_t out[8]={NIUSB_IBSIC_ID,0,0,0,NIUSB_TERM_ID,0,0,0}, in[16];
    int sent=0, received=0, r;
    struct ni_usb_status_block status;
    r=ni_usb_send_bulk_msg(p,out,sizeof(out),&sent,1000);
    if(r) return r;
    if(sent != sizeof(out)) return -EPROTO;
    r=ni_usb_receive_bulk_msg(p,in,sizeof(in),&received,1000,0);
    if(r) return r;
    if(received != 12) return -EPROTO;
    ni_usb_parse_status_block(in,&status);
    if(status.id != NIUSB_IBSIC_ID || status.error_code) return -EPROTO;
    ni_usb_soft_update_status(board,status.ibsta,0);
    return 0;
}
'''
    p.write_text(s, encoding="utf-8", newline="\n")

    diffs=[]
    manifest={"upstream":"https://github.com/northriv/KAME", "commit":COMMIT,
              "subdirectory":"modules/charinterface/usermode-linux-gpib",
              "linux_gpib_base":"4.3.6 / 9813ff8f", "license":"GPL-2.0-or-later", "files":{}}
    for rel, original in sorted(originals.items()):
        current=(dest/rel).read_bytes()
        manifest["files"][rel]={"upstream_sha256":hashlib.sha256(original).hexdigest(),
                                 "local_sha256":hashlib.sha256(current).hexdigest()}
        if current != original:
            diffs.extend(difflib.unified_diff(original.decode("utf-8").replace("\r\n", "\n").splitlines(True),
                         current.decode("utf-8").replace("\r\n", "\n").splitlines(True), fromfile="a/"+rel,tofile="b/"+rel))
    (ROOT/"UPSTREAM.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    (ROOT/"vendor/local-fixes.patch").write_text("".join(diffs),encoding="utf-8",newline="\n")
    print("Vendored",len(originals),"files at",COMMIT)


if __name__ == "__main__":
    main()
