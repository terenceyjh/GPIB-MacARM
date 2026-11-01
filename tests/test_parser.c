/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Run under address/undefined sanitizers; never opens USB or initializes driver. */
#include "compat.h"
#include "ni_usb_gpib.h"
#include <assert.h>
extern int parse_board_ibrd_readback(const uint8_t *,int,struct ni_usb_status_block *,uint8_t *,int,int *);
extern int kg_ni_parse_write_completion(const uint8_t *,int,size_t,struct ni_usb_status_block *);
int main(void)
{
    struct ni_usb_status_block status;
    uint8_t out[256]; int actual;
    /* Real EOI write ACK shape; missing/corrupt completions must not pass.
     * Bytes 6/7 are not specified by the upstream decoder and stay opaque. */
    uint8_t ack[12] = {0x0d,0,0x68,0,0,0,0,0,4,0,0,0};
    for (int count=1;count<=65535;count*=65535) {
        assert(kg_ni_parse_write_completion(ack,sizeof(ack),count,&status)==0);
        assert(status.id==0x0d && status.count==0 && status.error_code==0);
        if(count==65535)break;
    }
    for(int n=0;n<12;++n)
        assert(kg_ni_parse_write_completion(ack,n,6,&status)==-EPROTO);
    assert(kg_ni_parse_write_completion(NULL,12,6,&status)==-EPROTO);
    assert(kg_ni_parse_write_completion(ack,12,0,&status)==-EPROTO);
    assert(kg_ni_parse_write_completion(ack,12,65536,&status)==-EPROTO);
    assert(kg_ni_parse_write_completion(ack,12,6,NULL)==-EPROTO);
    for(int byte=8;byte<12;++byte) {
        ack[byte]^=1;
        assert(kg_ni_parse_write_completion(ack,12,6,&status)==-EPROTO);
        ack[byte]^=1;
    }
    ack[0]=0x0c;
    assert(kg_ni_parse_write_completion(ack,12,6,&status)==-EPROTO);
    ack[0]=0x0d;ack[4]=ack[5]=0xff; // one byte unconfirmed
    assert(kg_ni_parse_write_completion(ack,12,6,&status)==0 && status.count==1);
    ack[4]=0xf9; // seven bytes remaining exceeds the six-byte request
    assert(kg_ni_parse_write_completion(ack,12,6,&status)==-EPROTO);
    ack[4]=ack[5]=0;ack[3]=NIUSB_NO_LISTENER_ERROR;
    assert(kg_ni_parse_write_completion(ack,12,6,&status)==0 && status.error_code==NIUSB_NO_LISTENER_ERROR);
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
        (void)kg_ni_parse_write_completion(input,n,6,&status);
        free(input);
    }
    puts("parser: compact/full HS frames, truncations, 20000 malformed frames under sanitizers PASS");
    puts("write completion: real ACK, missing/truncated/corrupt/unrelated frames and residual bounds PASS");
    return 0;
}
