// SPDX-License-Identifier: GPL-2.0-or-later
// Exercise the actual C++ transport against an instrument that rejects UNT
// while a binary reply is in progress. No USB device is opened.
#define GPIB_MACARM_TEST
#define libusb_bulk_transfer kg_mock_bulk
#define libusb_control_transfer kg_mock_control
#define libusb_interrupt_transfer kg_mock_interrupt
#define kg_ni_ifc kg_mock_ifc
#include "../native/driver.cpp"
#include <cassert>

namespace {
struct BusModel {
    std::vector<uint8_t> reply{ '#','0',0,0xff,13,10,0,1,2,3,10 };
    size_t offset=0;
    int talker=-1, commands=0, reads=0, writes=0;
    bool live=false, fail_read=false, fail_cleanup=false, short_write=false;
} model;
struct RecoveryModel {
    int stop_result=8, stop_id=NI_USB_STOP_REQUEST, receives=0, ifcs=0, ifc_result=0;
    std::vector<std::pair<int,int>> completions{{LIBUSB_ERROR_TIMEOUT,0}};
} recovery;

int command(gpib_board_t *,uint8_t *data,size_t count,size_t *written) {
    ++model.commands;
    // The 2400 manual forbids untalking midway through a binary message.
    if (model.live) return -EPROTO;
    if (count==3 && data[0]==UNL && data[1]==MLA(0))
        model.talker=data[2]-MTA(0);
    if (count==2 && data[0]==UNL && data[1]==UNT) {
        if (model.fail_cleanup) return -EPROTO;
        model.talker=-1;
    }
    *written=count; return 0;
}
int read(gpib_board_t *,uint8_t *data,size_t size,int *end,size_t *count) {
    ++model.reads;
    assert(model.talker==24);
    if (model.fail_read) return -ETIMEDOUT;
    *count=std::min(size,model.reply.size()-model.offset);
    std::copy_n(model.reply.data()+model.offset,*count,data);
    model.offset+=*count;
    *end=model.offset==model.reply.size();
    model.live=!*end;
    return 0;
}
int write(gpib_board_t *,uint8_t *,size_t size,int,size_t *count) {
    ++model.writes;
    *count=model.short_write ? size-1 : size;
    return 0;
}
int enable_eos(gpib_board_t *,uint8_t,int) { return 0; }
void disable_eos(gpib_board_t *) {}
gpib_interface interface{};
std::string lifecycle;
void detach(gpib_board_t *) { lifecycle+='D'; }
void disconnect(usb_interface *) { lifecycle+='X'; }

template<class F> void fails(int kind,F operation) {
    try { operation(); assert(false); }
    catch(const Error &e) { assert(e.kind==kind); }
}
void reset() { model=BusModel{}; }
}

extern "C" int LIBUSB_CALL kg_mock_control(libusb_device_handle *,uint8_t,uint8_t request,
    uint16_t,uint16_t,unsigned char *data,uint16_t length,unsigned int) {
    assert(request==NI_USB_STOP_REQUEST && length==8);
    memset(data,0,length); data[0]=recovery.stop_id;
    return recovery.stop_result;
}
extern "C" int LIBUSB_CALL kg_mock_bulk(libusb_device_handle *,unsigned char,
    unsigned char *data,int length,int *actual,unsigned int) {
    assert(length>=16 && recovery.receives<int(recovery.completions.size()));
    auto step=recovery.completions[recovery.receives++];
    *actual=step.second; memset(data,0,*actual); return step.first;
}
extern "C" int LIBUSB_CALL kg_mock_interrupt(libusb_device_handle *,unsigned char,
    unsigned char *,int,int *actual,unsigned int) {
    *actual=0; return LIBUSB_ERROR_NO_DEVICE; // deterministic local polling-thread exit
}
extern "C" int kg_mock_ifc(gpib_board_t *) {
    ++recovery.ifcs; return recovery.ifc_result;
}

int main() {
    interface.command=command; interface.read=read; interface.write=write;
    interface.enable_eos=enable_eos; interface.disable_eos=disable_eos;
    uint8_t data[64]; int end;
    {
        reset(); Controller bus(&interface);
        std::vector<uint8_t> actual;
        for (int size : {2,1,3,2,64}) {
            size_t count=bus.read(24,data,size,-1,&end);
            actual.insert(actual.end(),data,data+count);
        }
        assert(actual==model.reply && end && model.commands==2);
    }
    {
        reset(); Controller bus(&interface);
        model.reply.assign(10000,0x0a);
        std::vector<uint8_t> buffer(65535), actual;
        while (actual.size()<model.reply.size()) {
            size_t count=bus.read(24,buffer.data(),buffer.size(),-1,&end);
            assert(count>0 && count<=4096);
            actual.insert(actual.end(),buffer.begin(),buffer.begin()+count);
        }
        assert(actual==model.reply && end && model.commands==2 && model.reads==3);
    }
    {
        reset(); Controller bus(&interface);
        assert(bus.read(24,data,2,-1,&end)==2 && !end);
        int before=model.commands;
        fails(INVALID,[&]{bus.read(8,data,1,-1,&end);});
        fails(INVALID,[&]{bus.write(24,data,1,true);});
        fails(INVALID,[&]{bus.clear(24);});
        fails(INVALID,[&]{bus.poll(24);});
        fails(INVALID,[&]{bus.ifc();});
        fails(INVALID,[&]{bus.remote(false);});
        assert(model.commands==before && model.reads==1 && model.writes==0);
        assert(bus.read(24,data,sizeof(data),-1,&end)==model.reply.size()-2 && end);
    }
    {
        reset(); Controller bus(&interface); model.fail_read=true;
        fails(TIMEOUT,[&]{bus.read(24,data,2,-1,&end);});
        assert(model.commands==1 && model.reads==1);
    }
    {
        reset(); Controller bus(&interface); model.short_write=true;
        fails(PROTOCOL,[&]{bus.write(24,data,2,true);});
        assert(model.commands==1 && model.writes==1);
    }
    {
        reset(); Controller bus(&interface); model.fail_cleanup=true;
        fails(PROTOCOL,[&]{bus.read(24,data,sizeof(data),-1,&end);});
        assert(model.commands==2 && model.reads==1);
    }
    {
        auto *original_driver=g_ni_usb_driver;
        auto *original_interface=g_ni_gpib_interface;
        usb_driver driver{}; driver.disconnect=disconnect; interface.detach=detach;
        g_ni_usb_driver=&driver; g_ni_gpib_interface=&interface;
        lifecycle.clear();
        kg_close(new Controller(&interface,true));
        assert(lifecycle=="DX"); // healthy close may shut down hardware first
        lifecycle.clear(); reset(); model.fail_read=true;
        auto *bus=new Controller(&interface,true);
        size_t count=0;
        assert(kg_read(bus,24,data,2,-1,&count,&end)==TIMEOUT);
        kg_close(bus);
        assert(lifecycle=="XD"); // failed close must cancel before detach
        lifecycle.clear(); reset();
        bus=new Controller(&interface,true);
        assert(kg_read(bus,24,data,2,-1,&count,&end)==0 && !end);
        kg_close(bus);
        assert(lifecycle=="XD"); // unfinished/over-limit replies also skip shutdown I/O
        g_ni_usb_driver=original_driver; g_ni_gpib_interface=original_interface;
    }
    // The real recover() must not touch the bus or restart status polling
    // until STOP and every queued late completion have been handled safely.
    auto recover_case=[&](int expected,int expected_ifcs) {
        reset(); usb_device device{};
        device.handle=reinterpret_cast<libusb_device_handle *>(1);
        ni_usb_private_t state{}; uint8_t interrupt_data[8]{};
        state.interrupt_urb=usb_alloc_urb(0,0);
        usb_fill_int_urb(state.interrupt_urb,&device,usb_rcvintpipe(&device,1),
                         interrupt_data,sizeof(interrupt_data),nullptr,nullptr,100);
        Controller bus(&interface,false,&state);
        int result=kg_recover(&bus,20);
        assert(result==expected && recovery.ifcs==expected_ifcs);
        if (expected==0) {
            assert(model.commands==1 && state.interrupt_urb->thread_started);
        } else {
            assert(model.commands==0 && !state.interrupt_urb->thread_started);
        }
        usb_kill_urb(state.interrupt_urb); usb_free_urb(state.interrupt_urb);
    };
    recovery=RecoveryModel{};
    recovery.completions={{0,16},{0,32},{LIBUSB_ERROR_TIMEOUT,0}};
    recover_case(0,1);
    assert(recovery.receives==3);
    recovery=RecoveryModel{}; recovery.stop_result=LIBUSB_ERROR_NO_DEVICE;
    recover_case(NOT_FOUND,0); assert(recovery.receives==0);
    recovery=RecoveryModel{}; recovery.stop_result=7;
    recover_case(PROTOCOL,0); assert(recovery.receives==0);
    recovery=RecoveryModel{}; recovery.stop_id=0;
    recover_case(PROTOCOL,0); assert(recovery.receives==0);
    recovery=RecoveryModel{}; recovery.completions={{LIBUSB_ERROR_NO_DEVICE,0}};
    recover_case(NOT_FOUND,0);
    recovery=RecoveryModel{}; recovery.completions={{LIBUSB_ERROR_TIMEOUT,5}};
    recover_case(TIMEOUT,0); // partial timed-out USB completion is not an empty pipe
    recovery=RecoveryModel{}; recovery.completions.assign(16,{0,16});
    recover_case(PROTOCOL,0); assert(recovery.receives==16);
    recovery=RecoveryModel{}; recovery.ifc_result=-ETIMEDOUT;
    recover_case(TIMEOUT,1);
    puts("driver: binary continuation, shared-bus isolation, failure/no-replay PASS");
    puts("recovery: late completions, unplug, malformed/partial status, bounded drain PASS");
}
