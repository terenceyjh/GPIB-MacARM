/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Run under address/undefined sanitizers; never opens USB or initializes driver. */
#include "compat.h"
#include "ni_usb_gpib.h"
#include <assert.h>
extern int parse_board_ibrd_readback(const uint8_t *,int,struct ni_usb_status_block *,uint8_t *,int,int *);
int main(void)
{
    struct ni_usb_status_block status;
    uint8_t out[256]; int actual;
    uint32_t seed=0x19ab;
    for(int trial=0;trial<20000;++trial) {
        seed=seed*1664525U+1013904223U;
        int n=(int)(seed%256);
        uint8_t *input=malloc(n ? n : 1);
        for(int i=0;i<n;++i) {seed=seed*1664525U+1013904223U;input[i]=(uint8_t)(seed>>24);}
        if(n>0 && trial%2==0) input[0]=trial%4 ? 0x36 : 0x37;
        (void)parse_board_ibrd_readback(input,n,&status,out,sizeof(out),&actual);
        free(input);
    }
    puts("parser: 20000 short/malformed frames under sanitizers PASS");
    return 0;
}
