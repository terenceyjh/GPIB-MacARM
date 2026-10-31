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
    /* Compact 7-byte count-limited read captured from the HS, anonymized. */
    uint8_t compact[32] = {
        0x36,'1','2','3','4','5','6','7',0,0,0,0,0,0,0,0,
        0x38,0,0x64,0,0,0,1,0,0x60,0x53,0,0,4,0,0,0
    };
    uint8_t full[44];
    const uint8_t registers_and_term[16] = {9,0,0,0,0,0,0,0,2,0,0,0,4,0,0,0};
    memcpy(full,compact,28);
    full[25]=7;
    memcpy(full+28,registers_and_term,sizeof(registers_and_term));
    assert(parse_board_ibrd_readback(compact,sizeof(compact),&status,out,7,&actual)==sizeof(compact));
    assert(actual==7 && memcmp(out,"1234567",7)==0);
    assert(parse_board_ibrd_readback(full,sizeof(full),&status,out,7,&actual)==sizeof(full));
    assert(actual==7 && memcmp(out,"1234567",7)==0);
    for(int n=0;n<sizeof(compact);++n)
        assert(parse_board_ibrd_readback(compact,n,&status,out,7,&actual)<0);
    for(int n=0;n<sizeof(full);++n)
        assert(parse_board_ibrd_readback(full,n,&status,out,7,&actual)<0);
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
    puts("parser: compact/full HS frames, truncations, 20000 malformed frames under sanitizers PASS");
    return 0;
}
