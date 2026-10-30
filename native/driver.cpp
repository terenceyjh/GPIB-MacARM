// SPDX-License-Identifier: GPL-2.0-or-later
// Standalone lifecycle/transport binding based on KAME NiGpibDriver (Kentaro
// Kitagawa, 2026). This C ABI is used by Python ctypes, not by the Python C API.
#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

extern "C" {
#include "compat.h"
#include "gpibP.h"
extern int ni_module_init(void);
extern void ni_module_exit(void);
extern struct usb_driver *g_ni_usb_driver;
extern struct gpib_interface *g_ni_gpib_interface;
extern int kg_ni_remote(gpib_board_t *, int);
extern int kg_ni_ifc(gpib_board_t *);
}

#define KG_EXPORT extern "C" __attribute__((visibility("default")))

namespace {
// Stable across operating systems; do not expose platform errno values to Python.
enum { IO=1, TIMEOUT=2, NOT_FOUND=3, BUSY=4, PROTOCOL=5, CLOSED=6, INVALID=7 };
class Error : public std::runtime_error {
public:
    int kind;
    Error(int k, const std::string &s) : std::runtime_error(s), kind(k) {}
};
thread_local std::string last_error, list_result;
std::mutex module_mutex;
int module_refs = 0;
struct Model { uint16_t pid; const char *name; };
const Model models[] = {{0x709b,"NI GPIB-USB-HS"}, {0x7618,"NI GPIB-USB-HS+"},
                       {0x702a,"NI GPIB-USB-B"}, {0x725c,"Keithley KUSB-488A"},
                       {0x725d,"MC USB-488"}};
const char *model_name(uint16_t pid) {
    for (const auto &m : models) if (m.pid == pid) return m.name;
    return nullptr;
}
void check(int r, const char *operation) {
    if (r >= 0) return;
    int kind = r == -ETIMEDOUT ? TIMEOUT : r == -ENODEV ? NOT_FOUND :
               (r == -EBUSY || r == -EACCES) ? BUSY :
               r == -EPROTO ? PROTOCOL : IO;
    throw Error(kind, std::string(operation) + ": " + strerror(-r) +
                      " (native errno " + std::to_string(-r) + ")");
}
void usb_check(int r, const char *op) {
    if (r >= 0) return;
    int kind = r == LIBUSB_ERROR_NO_DEVICE ? NOT_FOUND :
               r == LIBUSB_ERROR_TIMEOUT ? TIMEOUT :
               (r == LIBUSB_ERROR_BUSY || r == LIBUSB_ERROR_ACCESS) ? BUSY : IO;
    throw Error(kind, std::string(op) + ": " + libusb_error_name(r));
}
void address(int addr, int pad) {
    if (addr < 0 || addr > 30 || addr == pad)
        throw Error(INVALID, "Instrument address must be 0..30 and differ from controller address.");
}
std::string serial_of(libusb_device_handle *h, uint8_t descriptor) {
    if (!descriptor) return {};
    unsigned char b[256];
    int n = libusb_get_string_descriptor_ascii(h, descriptor, b, sizeof(b));
    return n > 0 ? std::string(reinterpret_cast<char *>(b), n) : std::string();
}
std::string escaped(const std::string &s) {
    std::string r = "\"";
    const char *hex = "0123456789abcdef";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { r += '\\'; r += c; }
        else if (c < 0x20 || c >= 0x7f) {
            r += "\\u00"; r += hex[c >> 4]; r += hex[c & 15];
        } else r += c;
    }
    return r + '"';
}

class Controller {
    libusb_context *ctx = nullptr;
    usb_device usb{};
    usb_interface intf{};
    gpib_board board{};
    bool registered = false, probed = false, attached = false, board_ready = false;
    int pad;
    void cleanup() noexcept {
        if (attached) { g_ni_gpib_interface->detach(&board); attached = false; }
        if (probed) { g_ni_usb_driver->disconnect(&intf); probed = false; }
        if (registered) {
            std::lock_guard<std::mutex> guard(module_mutex);
            if (--module_refs == 0) ni_module_exit();
            registered = false;
        }
        if (usb.handle) {
            libusb_release_interface(usb.handle, 0);
            libusb_close(usb.handle); usb.handle = nullptr;
        }
        if (ctx) { libusb_exit(ctx); ctx = nullptr; }
        // Matches exactly the pthread primitives initialized below; driver-owned
        // primitives are released by detach()/disconnect().
        if (board_ready) {
            pthread_mutex_destroy(&board.wait.lock);
            pthread_cond_destroy(&board.wait.cond);
            pthread_mutex_destroy(&board.spinlock);
            pthread_mutex_destroy(&board.locking_pid_spinlock);
            mutex_destroy(&board.user_mutex);
            mutex_destroy(&board.big_gpib_mutex);
            pthread_mutex_destroy(&board.event_queue.lock);
            pthread_mutex_destroy(&board.pseudo_irq.timer.lock);
            pthread_cond_destroy(&board.pseudo_irq.timer.cond);
            board_ready = false;
        }
    }
    void cmd(std::initializer_list<int> bytes) {
        uint8_t b[16]; size_t n=0, written=0;
        for (int v : bytes) b[n++] = static_cast<uint8_t>(v);
        check(board.interface->command(&board, b, n, &written), "GPIB command");
        if (written != n) throw Error(PROTOCOL, "Short GPIB command transfer.");
    }
    void unaddress() noexcept {
        try { cmd({UNL, UNT}); } catch (...) {}
    }
    void drain(libusb_device *d) {
        libusb_config_descriptor *cfg = nullptr;
        if (libusb_get_active_config_descriptor(d, &cfg) != 0) return;
        if (cfg->bNumInterfaces && cfg->interface[0].num_altsetting) {
            const auto &alt = cfg->interface[0].altsetting[0];
            for (int e=0; e<alt.bNumEndpoints; ++e) {
                const auto &ep = alt.endpoint[e];
                libusb_clear_halt(usb.handle, ep.bEndpointAddress);
                if (!(ep.bEndpointAddress & LIBUSB_ENDPOINT_IN)) continue;
                unsigned char data[4096];
                for (int tries=0; tries<16; ++tries) {
                    int got=0;
                    int r = ((ep.bmAttributes & LIBUSB_TRANSFER_TYPE_MASK) == LIBUSB_TRANSFER_TYPE_INTERRUPT)
                        ? libusb_interrupt_transfer(usb.handle, ep.bEndpointAddress, data, sizeof(data), &got, 20)
                        : libusb_bulk_transfer(usb.handle, ep.bEndpointAddress, data, sizeof(data), &got, 20);
                    if (r != 0 || got == 0) break;
                }
            }
        }
        libusb_free_config_descriptor(cfg);
    }
public:
    std::mutex mutex;
    Controller(int index, int board_pad, unsigned timeout, const char *serial) : pad(board_pad) {
        if (pad < 0 || pad > 30 || index < 0) throw Error(INVALID, "Invalid controller address or adapter index.");
        try {
            usb_check(libusb_init(&ctx), "libusb_init");
            libusb_device **devices = nullptr;
            ssize_t count = libusb_get_device_list(ctx, &devices);
            usb_check(static_cast<int>(count < 0 ? count : 0), "USB enumeration");
            try {
                int matched=0;
                for (ssize_t i=0; i<count; ++i) {
                    libusb_device_descriptor desc{};
                    if (libusb_get_device_descriptor(devices[i], &desc) != 0 ||
                        desc.idVendor != 0x3923 || !model_name(desc.idProduct)) continue;
                    bool by_serial = serial && *serial;
                    if (!by_serial && matched++ != index) continue;
                    libusb_device_handle *h=nullptr;
                    int r=libusb_open(devices[i], &h);
                    if (r != 0 && by_serial) continue;
                    usb_check(r, "Opening USB adapter (check permissions/other drivers)");
                    if (by_serial && serial_of(h, desc.iSerialNumber) != serial) { libusb_close(h); continue; }
                    usb.handle=h;
                    libusb_set_auto_detach_kernel_driver(h, 1);
                    int configuration=0;
                    if (libusb_get_configuration(h, &configuration) == 0 && configuration > 0)
                        libusb_set_configuration(h, configuration); // best effort before claim
                    usb_check(libusb_claim_interface(h, 0), "Claiming USB interface (another process or NI driver may own it)");
                    drain(devices[i]);
                    usb.descriptor.idVendor=desc.idVendor; usb.descriptor.idProduct=desc.idProduct;
                    usb.devnum=libusb_get_device_address(devices[i]);
                    usb._bus_storage.busnum=libusb_get_bus_number(devices[i]); usb.bus=&usb._bus_storage;
                    snprintf(usb.dev.name, sizeof(usb.dev.name), "usb%d-%d", usb.bus->busnum, usb.devnum);
                    break;
                }
            } catch (...) { libusb_free_device_list(devices, 1); throw; }
            libusb_free_device_list(devices, 1);
            if (!usb.handle) throw Error(NOT_FOUND, "No matching NI USB-GPIB adapter found. Run gpib-macarm list; check model, serial and permissions.");
            intf.udev=&usb;
            {
                std::lock_guard<std::mutex> guard(module_mutex);
                if (module_refs == 0) check(ni_module_init(), "NI driver initialization");
                ++module_refs; registered=true;
            }
            if (!g_ni_usb_driver || !g_ni_gpib_interface) throw Error(IO,"Driver registration failed.");
            usb_device_id id{}; id.idVendor=usb.descriptor.idVendor;
            id.idProduct=usb.descriptor.idProduct; id.bInterfaceNumber=-1;
            check(g_ni_usb_driver->probe(&intf,&id), "NI USB probe"); probed=true;
            board.interface=g_ni_gpib_interface; board.pad=pad; board.sad=-1;
            board.master=1; board.usec_timeout=timeout;
            init_waitqueue_head(&board.wait); spin_lock_init(&board.spinlock);
            spin_lock_init(&board.locking_pid_spinlock);
            mutex_init(&board.user_mutex); mutex_init(&board.big_gpib_mutex);
            board_ready=true;
            INIT_LIST_HEAD(&board.device_list); init_event_queue(&board.event_queue);
            init_gpib_pseudo_irq(&board.pseudo_irq);
            gpib_board_config cfg{};
            int r=board.interface->attach(&board,&cfg);
            if (r < 0) { board.interface->detach(&board); check(r,"NI driver attach"); }
            attached=true;
            check(kg_ni_remote(&board,1),"Enable remote (REN)");
            check(kg_ni_ifc(&board),"Interface clear (IFC)");
        } catch (...) { cleanup(); throw; }
    }
    ~Controller() { cleanup(); }
    void timeout(unsigned us) {
        if (!us || us > 1000000000U) throw Error(INVALID,"Timeout must be 1..1000000000 microseconds.");
        board.usec_timeout=us;
    }
    size_t write(int addr, const uint8_t *data, size_t size, bool eoi) {
        address(addr,pad);
        if (!size || size>65535) throw Error(INVALID,"One native write must contain 1..65535 bytes.");
        size_t written=0;
        try {
            cmd({MTA(static_cast<uint32_t>(pad)),UNL,MLA(static_cast<uint32_t>(addr))});
            int r=board.interface->write(&board,const_cast<uint8_t *>(data),size,eoi,&written);
            unaddress(); check(r,"GPIB write (not automatically retried)");
        } catch (...) { unaddress(); throw; }
        if (written != size) throw Error(PROTOCOL,"Short GPIB write; command may have partially executed.");
        return written;
    }
    size_t read(int addr,uint8_t *data,size_t size,int eos,int *end) {
        address(addr,pad);
        if (!size || size>65535 || eos < -1 || eos > 255) throw Error(INVALID,"Invalid read size or EOS.");
        size_t count=0; *end=0;
        board.interface->disable_eos(&board);
        try {
            if (eos>=0) check(board.interface->enable_eos(&board,static_cast<uint8_t>(eos),1),"Enable EOS");
            cmd({UNL,MLA(static_cast<uint32_t>(pad)),MTA(static_cast<uint32_t>(addr))});
            int r=board.interface->read(&board,data,size,end,&count);
            board.interface->disable_eos(&board); unaddress(); check(r,"GPIB read");
        } catch (...) { board.interface->disable_eos(&board); unaddress(); throw; }
        if (count>size) throw Error(PROTOCOL,"Driver returned an invalid byte count.");
        return count;
    }
    void clear(int addr) {
        address(addr,pad);
        try { cmd({UNL,MLA(static_cast<uint32_t>(addr)),SDC}); unaddress(); }
        catch (...) { unaddress(); throw; }
    }
    void ifc() { check(kg_ni_ifc(&board),"Interface clear (IFC)"); }
    void remote(bool enabled) { check(kg_ni_remote(&board,enabled),"Set remote (REN)"); }
    uint8_t poll(int addr) {
        address(addr,pad); uint8_t b=0; size_t n=0; int end=0;
        try {
            cmd({UNL,MLA(static_cast<uint32_t>(pad)),SPE}); cmd({MTA(static_cast<uint32_t>(addr))});
            int r=board.interface->read(&board,&b,1,&end,&n);
            cmd({SPD,UNL,UNT}); check(r,"Serial poll");
        } catch (...) { try {cmd({SPD,UNL,UNT});} catch (...) {} throw; }
        if (n!=1) throw Error(PROTOCOL,"Serial poll returned no status byte.");
        return b;
    }
    bool srq() {
        int r=board.interface->line_status(&board); check(r,"Read GPIB bus lines");
        return (r & BUS_SRQ)!=0;
    }
};

template<class F> int call(F fn) noexcept {
    last_error.clear();
    try { fn(); return 0; }
    catch (const Error &e) { last_error=e.what(); return e.kind; }
    catch (const std::exception &e) { last_error=e.what(); return IO; }
    catch (...) { last_error="Unknown native exception."; return IO; }
}
template<class F> int handle_device(void *p,F fn) noexcept {
    return call([&] {
        if (!p) throw Error(CLOSED,"Controller is closed.");
        auto &d=*static_cast<Controller *>(p);
        std::lock_guard<std::mutex> guard(d.mutex); fn(d);
    });
}
}

KG_EXPORT const char *kg_version() { return "0.1.0"; }
KG_EXPORT const char *kg_last_error() { return last_error.c_str(); }
KG_EXPORT int kg_open(int index,int pad,unsigned timeout,const char *serial,void **result) {
    if (result) *result=nullptr;
    return call([&] {
        if (!result || !timeout || timeout>1000000000U) throw Error(INVALID,"Invalid open arguments.");
        *result=new Controller(index,pad,timeout,serial);
    });
}
KG_EXPORT void kg_close(void *p) { delete static_cast<Controller *>(p); }
KG_EXPORT int kg_timeout(void *p,unsigned us) { return handle_device(p,[&](auto &d){d.timeout(us);}); }
KG_EXPORT int kg_write(void *p,int addr,const uint8_t *data,size_t size,int eoi,size_t *written) {
    return handle_device(p,[&](auto &d){if (!data || !written) throw Error(INVALID,"Null output/data."); *written=d.write(addr,data,size,eoi!=0);});
}
KG_EXPORT int kg_read(void *p,int addr,uint8_t *data,size_t size,int eos,size_t *count,int *end) {
    return handle_device(p,[&](auto &d){if (!data || !count || !end) throw Error(INVALID,"Null output/data."); *count=d.read(addr,data,size,eos,end);});
}
KG_EXPORT int kg_clear(void *p,int addr) { return handle_device(p,[&](auto &d){d.clear(addr);}); }
KG_EXPORT int kg_ifc(void *p) { return handle_device(p,[](auto &d){d.ifc();}); }
KG_EXPORT int kg_remote(void *p,int on) { return handle_device(p,[&](auto &d){d.remote(on!=0);}); }
KG_EXPORT int kg_poll(void *p,int addr,int *stb) { return handle_device(p,[&](auto &d){if(!stb) throw Error(INVALID,"Null output."); *stb=d.poll(addr);}); }
KG_EXPORT int kg_srq(void *p,int *srq) { return handle_device(p,[&](auto &d){if(!srq) throw Error(INVALID,"Null output."); *srq=d.srq();}); }
KG_EXPORT int kg_list(const char **result) {
    return call([&] {
        if (!result) throw Error(INVALID,"Null output.");
        libusb_context *ctx=nullptr; usb_check(libusb_init(&ctx),"libusb_init");
        libusb_device **devices=nullptr;
        ssize_t n=libusb_get_device_list(ctx,&devices);
        if(n<0) {libusb_exit(ctx); usb_check(static_cast<int>(n),"USB enumeration");}
        try {
            std::ostringstream out; out << '['; int index=0;
            for(ssize_t i=0;i<n;++i) {
                libusb_device_descriptor d{};
                if(libusb_get_device_descriptor(devices[i],&d)!=0 || d.idVendor!=0x3923 || !model_name(d.idProduct)) continue;
                libusb_device_handle *h=nullptr; std::string serial;
                int access=libusb_open(devices[i],&h);
                if(access==0) {serial=serial_of(h,d.iSerialNumber); libusb_close(h);}
                if(index) out << ',';
                out << "{\"index\":" << index++ << ",\"model\":" << escaped(model_name(d.idProduct))
                    << ",\"vendor_id\":14627,\"product_id\":" << d.idProduct
                    << ",\"bus\":" << int(libusb_get_bus_number(devices[i]))
                    << ",\"address\":" << int(libusb_get_device_address(devices[i]))
                    << ",\"serial\":" << (serial.empty()?"null":escaped(serial))
                    << ",\"accessible\":" << (access==0?"true":"false") << '}';
            }
            out << ']'; list_result=out.str();
        } catch (...) {libusb_free_device_list(devices,1);libusb_exit(ctx);throw;}
        libusb_free_device_list(devices,1);libusb_exit(ctx);
        *result=list_result.c_str();
    });
}
