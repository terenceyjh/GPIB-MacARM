/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Exercise actual bulk-URB shim without accessing a USB device. */
#define libusb_bulk_transfer kg_mock_bulk_transfer
#include "compat.h"
#include <assert.h>
static unsigned observed_timeout;
static int answer, callbacks;
int LIBUSB_CALL kg_mock_bulk_transfer(libusb_device_handle *h,unsigned char ep,
    unsigned char *data,int length,int *actual,unsigned timeout)
{
    (void)h; (void)ep; (void)data;
    observed_timeout=timeout; *actual=length; return answer;
}
static void done(struct urb *u) { (void)u; ++callbacks; }
int main(void)
{
    struct usb_device d={0}; unsigned char data[8]={0};
    d.handle=(libusb_device_handle *)1;
    struct urb *u=usb_alloc_urb(0,0);
    usb_fill_bulk_urb(u,&d,usb_sndbulkpipe(&d,2),data,sizeof(data),done,NULL);
    u->timeout_ms=32000;
    answer=0; assert(usb_submit_urb(u,0)==0);
    assert(observed_timeout==32000 && u->actual_length==8 && u->status==0);
    answer=LIBUSB_ERROR_TIMEOUT; usb_submit_urb(u,0); assert(u->status==-ETIMEDOUT);
    answer=LIBUSB_ERROR_NO_DEVICE; usb_submit_urb(u,0); assert(u->status==-ENODEV);
    assert(callbacks==3); usb_free_urb(u);
    puts("compat: dynamic timeout and USB error identity PASS");
    return 0;
}
