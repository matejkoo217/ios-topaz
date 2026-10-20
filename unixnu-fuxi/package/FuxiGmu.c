/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "FuxiGmu.h"
#include "AdrenoFirmware.h"
/* Generated only from exact pinned XML/catalog/DT/firmware policy; ignored.
 * In particular, no vendor firmware or sequencer payload is stored in Git. */
#include "FuxiGmuSource.h"
#if !defined(__aarch64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error fuxi GMU requires little-endian AArch64
#endif
static int extent(uintptr_t at,size_t bytes)
{return at && bytes && bytes-1<=UINTPTR_MAX-at;}
static int overlap(uintptr_t a,size_t na,uintptr_t b,size_t nb)
{return a<=b?(b-a<na):(a-b<nb);}
static size_t core_offset(uint32_t word)
{return ((size_t)word<<2)-SHENG_GMU_CORE_GPU_DELTA;}
static int read32(FuxiGmuDevice *d,unsigned window,size_t at,uint32_t *v,FuxiGmuResult *r)
{++r->read_attempts;return d->io.read32(d->io.cookie,window,at,v);}
static int write32(FuxiGmuDevice *d,unsigned window,size_t at,uint32_t v,FuxiGmuResult *r)
{++r->write_attempts;return d->io.write32(d->io.cookie,window,at,v);}
static int core_read(FuxiGmuDevice *d,uint32_t word,uint32_t *v,FuxiGmuResult *r)
{return read32(d,FuxiGmuCore,core_offset(word),v,r);}
static int core_write(FuxiGmuDevice *d,uint32_t word,uint32_t v,FuxiGmuResult *r)
{return write32(d,FuxiGmuCore,core_offset(word),v,r);}
static FuxiGmuStatus check_faults(FuxiGmuDevice *d,FuxiGmuResult *r)
{
    if(core_read(d,REG_GMU_AO_HOST_INTERRUPT_STATUS,&r->ao_fault_status,r) ||
        core_read(d,REG_GMU_GMU2HOST_INTR_INFO,&r->cm3_fault_status,r))return FuxiGmuIoError;
    return (r->ao_fault_status&SHENG_GMU_AO_FATAL_MASK) ||
        (r->cm3_fault_status&SHENG_GMU_CM3_FATAL_MASK)?FuxiGmuFault:FuxiGmuSuccess;
}
static int notify(void *cookie)
{
    FuxiGmuDevice *d=cookie;
    return d->io.barrier(d->io.cookie) ||
        d->io.write32(d->io.cookie,FuxiGmuCore,core_offset(REG_GMU_HOST2GMU_INTR_SET),1) ||
        d->io.barrier(d->io.cookie);
}
static FuxiGmuStatus poll(FuxiGmuDevice *d,uint32_t reg,uint32_t mask,
    uint32_t expected,unsigned budget,uint32_t *observed,FuxiGmuResult *r)
{
    uint64_t start,last,now;
    if(d->services.now_us(d->services.cookie,&start))return FuxiGmuClockError;
    last=start;
    for(unsigned i=0;i<budget;++i) {
        if(d->services.now_us(d->services.cookie,&now) || now<last)return FuxiGmuClockError;
        if(now-start>=10000)return FuxiGmuTimeout;
        last=now;++r->poll_reads;
        FuxiGmuStatus fault=check_faults(d,r);if(fault!=FuxiGmuSuccess)return fault;
        if(core_read(d,reg,observed,r))return FuxiGmuIoError;
        if((*observed&mask)==expected) {
            if(d->io.barrier(d->io.cookie))return FuxiGmuIoError;
            return FuxiGmuSuccess;
        }
        if(i+1<budget && d->services.wait_us(d->services.cookie,100))return FuxiGmuClockError;
    }
    return FuxiGmuTimeout;
}
static void reset_after_failure(FuxiGmuDevice *d,FuxiGmuResult *r)
{
    uint32_t actual;r->reset_verified=0;d->poisoned=1;d->hfi.poisoned=1;
    if(!core_write(d,REG_GMU_CM3_SYSRESET,1,r) && !d->io.barrier(d->io.cookie) &&
        !core_read(d,REG_GMU_CM3_SYSRESET,&actual,r) && actual==1)r->reset_verified=1;
}
static uint32_t le32(const uint8_t *p)
{return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static FuxiGmuStatus validate(FuxiGmuDevice *d,const FuxiGmuConfig *c,FuxiGmuResult *r)
{
    if(!d || !c || !d->io.read32 || !d->io.write32 || !d->io.barrier ||
        !d->services.sha256 || !d->services.now_us || !d->services.wait_us ||
        c->chip_id!=SHENG_GMU_CHIP_ID || !c->firmware || c->firmware_bytes!=SHENG_GMU_FIRMWARE_BYTES ||
        !extent((uintptr_t)c->firmware,c->firmware_bytes) || !c->poll_budget || c->poll_budget>1024)
        return FuxiGmuArgument;
    if(d->poisoned)return FuxiGmuPoisoned;
    if(d->boot_attempted)return FuxiGmuBusy;
    for(unsigned i=0;i<FuxiGmuWindows;++i)if(d->io.bytes[i]!=fuxi_gmu_window_bytes[i])return FuxiGmuArgument;
    const FuxiGmuMemory *mem[]={&c->icache,&c->dummy,&c->debug,&c->log,&c->hfi};
    const size_t sizes[]={0xffc000,0x4000,0x7000,0x4000,0x4000};
    for(unsigned i=0;i<5;++i) {
        const FuxiGmuMemory *m=mem[i];
        if(m->bytes!=sizes[i] || !extent((uintptr_t)m->cpu,m->bytes) || ((uintptr_t)m->cpu&4095) ||
            !m->iova || (m->iova&4095) || m->iova>UINT32_MAX-(m->bytes-1) ||
            overlap((uintptr_t)m->cpu,m->bytes,(uintptr_t)c->firmware,c->firmware_bytes))return FuxiGmuArgument;
        for(unsigned j=0;j<i;++j)if(overlap((uintptr_t)m->cpu,m->bytes,(uintptr_t)mem[j]->cpu,mem[j]->bytes) ||
            overlap((uintptr_t)m->iova,m->bytes,(uintptr_t)mem[j]->iova,mem[j]->bytes))return FuxiGmuArgument;
    }
    if(c->icache.iova!=0x4000 || c->dummy.iova!=0x60000000 || c->debug.iova!=0x60400000)return FuxiGmuArgument;
    if(d->services.sha256(d->services.cookie,c->firmware,c->firmware_bytes,r->complete_sha256))return FuxiGmuFirmware;
    for(unsigned i=0;i<32;++i)if(r->complete_sha256[i]!=fuxi_gmu_firmware_sha256[i])return FuxiGmuFirmware;
    r->complete_hash_verified=1;return FuxiGmuSuccess;
}
FuxiGmuStatus FuxiGmuLoadAndStartHfi(FuxiGmuDevice *d,const FuxiGmuConfig *c,FuxiGmuResult *r)
{
    if(!r)return FuxiGmuArgument;
    *r=(FuxiGmuResult){0};r->resources_must_retain=1;
    FuxiGmuStatus status=validate(d,c,r);if(status!=FuxiGmuSuccess)return status;
    const AdrenoFirmwareRegion regions[]={{0,0x4000,1},{0x4000,0xffc000,2},{0x10004000,0x4000,3}};
    AdrenoFirmwareBlock blocks[32];size_t count=0;
    if(AdrenoFirmwarePlanGmu(c->firmware,c->firmware_bytes,regions,3,blocks,32,&count)!=AdrenoFirmwareSuccess || count!=15)
        return FuxiGmuFirmware;
    r->phase=1;uint32_t value;
    if(core_read(d,REG_GMU_CM3_SYSRESET,&value,r))return FuxiGmuIoError;
    if(value!=1)return FuxiGmuBusy;
    r->reset_verified=1;
    if(read32(d,FuxiGmuCxMisc,REG_CX_MISC_TCM_RET_CNTL*4,&value,r))return FuxiGmuIoError;
    if(value)return FuxiGmuStateMismatch;
    if(read32(d,FuxiGmuRscc,REG_RSCC_SEQ_BUSY_DRV0*4,&value,r))return FuxiGmuIoError;
    if(value)return FuxiGmuBusy;
    if(core_read(d,REG_GMU_HFI_CTRL_STATUS,&value,r))return FuxiGmuIoError;
    if(value&1)return FuxiGmuStateMismatch; /* A stale ready bit cannot pass. */
    status=check_faults(d,r);if(status!=FuxiGmuSuccess)return status;
    r->phase=2;
    d->boot_attempted=1;
    for(unsigned i=0;i<SHENG_GMU_RSC_SETUP_COUNT;++i) {
        const FuxiGmuSetupWrite *w=fuxi_gmu_rsc_setup+i;
        if(write32(d,w->window,w->byte_offset,w->value,r)) {status=FuxiGmuIoError;goto failed;}
    }
    if(d->io.barrier(d->io.cookie)) {status=FuxiGmuIoError;goto failed;}
    if(core_write(d,REG_GPU_GMU_CX_GMU_CX_FALNEXT_INTF,1,r) ||
        core_write(d,REG_GPU_GMU_CX_GMU_CX_FAL_INTF,1,r) ||
        write32(d,FuxiGmuCxMisc,REG_CX_MISC_TCM_RET_CNTL*4,1,r)) {status=FuxiGmuIoError;goto failed;}
    if(d->io.barrier(d->io.cookie) || read32(d,FuxiGmuCxMisc,REG_CX_MISC_TCM_RET_CNTL*4,&value,r)) {status=FuxiGmuIoError;goto failed;}
    if(value!=1) {status=FuxiGmuStateMismatch;goto failed;}
    /* All shared allocations are real owned coherent memory, not simulated
     * GMU addresses. Zero only after actual stopped/idle checks above. */
    const FuxiGmuMemory *memory[]={&c->icache,&c->dummy,&c->debug,&c->log};
    r->memory_changed=1;
    for(unsigned m=0;m<4;++m)for(size_t i=0;i<memory[m]->bytes/4;++i)memory[m]->cpu[i]=0;
    if(AdrenoHfiInitializeStopped(&d->hfi,c->hfi.cpu,c->hfi.bytes,c->hfi.iova,d,notify)!=AdrenoHfiSuccess) {
        status=FuxiGmuArgument;goto failed;
    }
    r->phase=3;
    for(size_t i=0;i<count;++i) {
        const AdrenoFirmwareBlock *b=blocks+i;
        /* Zero-size records authorize no allocation or write. The pinned
         * loader skips them; all real extents were independently supplied. */
        if(!b->bytes)continue;
        for(size_t at=0;at<b->bytes;at+=4) {
            uint32_t word=le32(c->firmware+b->payload_offset+at);
            if(b->region_identifier==2)c->icache.cpu[(b->address-0x4000+at)/4]=word;
            else {
                uint32_t reg=b->region_identifier==1?REG_GMU_CM3_ITCM_START+b->address/4:
                    REG_GMU_CM3_DTCM_START+(b->address-0x10004000)/4;
                if(core_write(d,reg+(uint32_t)(at/4),word,r)) {status=FuxiGmuIoError;goto failed;}
            }
        }
    }
    if(d->io.barrier(d->io.cookie)) {status=FuxiGmuIoError;goto failed;}
    /* Read every TCM payload word before releasing reset. CPU cache readback
     * checks copied bytes only; actual GMU coherency is still a prerequisite. */
    for(size_t i=0;i<count;++i) {
        const AdrenoFirmwareBlock *b=blocks+i;
        for(size_t at=0;at<b->bytes;at+=4) {
            if(b->region_identifier==2)value=c->icache.cpu[(b->address-0x4000+at)/4];
            else {
                uint32_t reg=b->region_identifier==1?REG_GMU_CM3_ITCM_START+b->address/4:
                    REG_GMU_CM3_DTCM_START+(b->address-0x10004000)/4;
                if(core_read(d,reg+(uint32_t)(at/4),&value,r)) {status=FuxiGmuIoError;goto failed;}
            }
            if(value!=le32(c->firmware+b->payload_offset+at)) {status=FuxiGmuStateMismatch;goto failed;}
        }
    }
    r->phase=4;
    if(core_write(d,REG_GMU_CM3_FW_INIT_RESULT,0,r) ||
        core_write(d,REG_GMU_CM3_BOOT_CONFIG,2,r) ||
        core_write(d,REG_GMU_HFI_QTBL_ADDR,(uint32_t)c->hfi.iova,r) ||
        core_write(d,REG_GMU_HFI_QTBL_INFO,1,r) ||
        core_write(d,REG_GMU_AHB_FENCE_RANGE_0,UINT32_C(0x80000000)|(0x32u<<18)|0x8a0,r) ||
        core_write(d,REG_GMU_CM3_CFG,0x4052,r) ||
        core_write(d,REG_GMU_GENERAL_10,SHENG_GMU_FW_CHIP_ID,r) ||
        core_write(d,REG_GMU_GENERAL_8,(uint32_t)c->log.iova|3,r)) {status=FuxiGmuIoError;goto failed;}
    for(unsigned i=0;i<4;++i)if(write32(d,FuxiGmuGpu,(REG_GBIF_QSB_SIDE0+i)*4,0x71620,r)) {status=FuxiGmuIoError;goto failed;}
    if(core_write(d,REG_GMU_SYS_BUS_CONFIG,1,r) || core_write(d,REG_GMU_ICACHE_CONFIG,1,r) ||
        core_write(d,REG_GMU_DCACHE_CONFIG,1,r) || core_read(d,REG_GMU_CM3_DTCM_START+0xff8,&value,r)) {status=FuxiGmuIoError;goto failed;}
    uint32_t mask=value<=UINT32_C(0x20010004)?UINT32_MAX:0x1ff;
    uint32_t ready=mask==UINT32_MAX?UINT32_C(0xbabeface):0x100;
    if(core_write(d,REG_GMU_CM3_SYSRESET,1,r) || core_write(d,REG_GMU_GENERAL_9,0,r) ||
        d->io.barrier(d->io.cookie)) {status=FuxiGmuIoError;goto failed;}
    const uint32_t config_regs[]={REG_GMU_CM3_FW_INIT_RESULT,REG_GMU_CM3_BOOT_CONFIG,
        REG_GMU_HFI_QTBL_ADDR,REG_GMU_HFI_QTBL_INFO,REG_GMU_CM3_CFG,REG_GMU_GENERAL_10,
        REG_GMU_GENERAL_8,REG_GMU_AHB_FENCE_RANGE_0,REG_GMU_SYS_BUS_CONFIG,
        REG_GMU_ICACHE_CONFIG,REG_GMU_DCACHE_CONFIG};
    const uint32_t config_values[]={0,2,(uint32_t)c->hfi.iova,1,0x4052,SHENG_GMU_FW_CHIP_ID,
        (uint32_t)c->log.iova|3,UINT32_C(0x80000000)|(0x32u<<18)|0x8a0,1,1,1};
    for(unsigned i=0;i<sizeof(config_regs)/sizeof(config_regs[0]);++i) {
        if(core_read(d,config_regs[i],&value,r)) {status=FuxiGmuIoError;goto failed;}
        if(value!=config_values[i]) {status=FuxiGmuStateMismatch;goto failed;}
    }
    r->reset_verified=0;
    if(core_write(d,REG_GMU_CM3_SYSRESET,0,r) || d->io.barrier(d->io.cookie)) {status=FuxiGmuIoError;goto failed;}
    r->phase=5;
    status=poll(d,REG_GMU_CM3_FW_INIT_RESULT,mask,ready,c->poll_budget,&r->firmware_init_result,r);
    if(status!=FuxiGmuSuccess)goto failed;
    r->firmware_ready_observed=1;
    if(core_write(d,REG_GMU_HFI_CTRL_INIT,1,r) || d->io.barrier(d->io.cookie)) {status=FuxiGmuIoError;goto failed;}
    r->phase=6;
    status=poll(d,REG_GMU_HFI_CTRL_STATUS,1,1,c->poll_budget,&r->hfi_status,r);
    if(status!=FuxiGmuSuccess)goto failed;
    status=check_faults(d,r);if(status!=FuxiGmuSuccess)goto failed;
    if(d->io.barrier(d->io.cookie)) {status=FuxiGmuIoError;goto failed;}
    r->hfi_ready_observed=1;r->phase=7;return FuxiGmuSuccess;
failed:
    reset_after_failure(d,r);return status;
}
typedef struct {
    FuxiGmuDevice *device;
    FuxiGmuStartupResult *result;
} StartupContext;
static int startup_now(void *cookie,uint64_t *value)
{
    FuxiGmuDevice *d=((StartupContext *)cookie)->device;
    return d->services.now_us(d->services.cookie,value);
}
static int startup_wait(void *cookie,unsigned us)
{
    FuxiGmuDevice *d=((StartupContext *)cookie)->device;
    return d->services.wait_us(d->services.cookie,us);
}
static int startup_health(void *cookie)
{
    StartupContext *c=cookie;FuxiGmuDevice *d=c->device;
    FuxiGmuStartupResult *r=c->result;uint32_t reset,status;
    r->health_status=check_faults(d,&r->load);
    if(r->health_status!=FuxiGmuSuccess)return 1;
    if(core_read(d,REG_GMU_CM3_SYSRESET,&reset,&r->load) ||
        core_read(d,REG_GMU_HFI_CTRL_STATUS,&status,&r->load))r->health_status=FuxiGmuIoError;
    else if(reset!=0 || !(status&1))r->health_status=FuxiGmuStateMismatch;
    return r->health_status!=FuxiGmuSuccess;
}
FuxiGmuStatus FuxiGmuColdStart(FuxiGmuDevice *d,const FuxiGmuConfig *c,
    const AdrenoHfiStartupConfig *config,const FuxiGmuStartupLimits *limits,FuxiGmuStartupResult *r)
{
    if(!r)return FuxiGmuArgument;
    *r=(FuxiGmuStartupResult){0};r->load.resources_must_retain=r->protocol.resources_must_retain=1;
    r->protocol_status=AdrenoHfiStartupInvalid; /* Not attempted until the load succeeds. */
    if(!d || !c || !limits || AdrenoHfiStartupValidate(config)!=AdrenoHfiStartupSuccess)return FuxiGmuArgument;
    StartupContext context={d,r};
    AdrenoHfiStartupServices services={&context,startup_now,startup_wait,startup_health,
        limits->polls_per_command,limits->wait_interval_us,limits->command_timeout_us,limits->total_timeout_us};
    if(AdrenoHfiStartupValidateServices(&services)!=AdrenoHfiStartupSuccess)return FuxiGmuArgument;
    if(d->poisoned || d->startup.poisoned)return FuxiGmuPoisoned;
    if(d->startup.attempted || d->startup.completed)return FuxiGmuBusy;
    FuxiGmuStatus status=FuxiGmuLoadAndStartHfi(d,c,&r->load);
    if(status!=FuxiGmuSuccess)return status;
    r->protocol_status=AdrenoHfiStartupRun(&d->startup,&d->hfi,config,&services,&r->protocol);
    if(r->protocol_status==AdrenoHfiStartupSuccess)return FuxiGmuSuccess;
    switch(r->protocol_status) {
    case AdrenoHfiStartupClockError:case AdrenoHfiStartupWaitError:status=FuxiGmuClockError;break;
    case AdrenoHfiStartupTimeout:status=FuxiGmuTimeout;break;
    case AdrenoHfiStartupPlatformFault:status=r->health_status;break;
    default:status=FuxiGmuProtocolError;break;
    }
    reset_after_failure(d,&r->load);d->startup.poisoned=1;
    return status;
}
static int fits(FuxiGmuMmio *m,unsigned window,size_t at)
{
    if(!m || window>=FuxiGmuWindows)return 0;
    FuxiGmuMmioWindow *w=m->windows+window;
    return extent((uintptr_t)w->cpu,w->bytes) && !((uintptr_t)w->cpu&3) && !(at&3) &&
        at<=w->bytes && w->bytes-at>=4;
}
static int mmio_read(void *cookie,unsigned window,size_t at,uint32_t *v)
{FuxiGmuMmio *m=cookie;if(!v || !fits(m,window,at))return 1;*v=*(volatile uint32_t *)(m->windows[window].cpu+at);return 0;}
static int mmio_write(void *cookie,unsigned window,size_t at,uint32_t v)
{FuxiGmuMmio *m=cookie;if(!fits(m,window,at))return 1;*(volatile uint32_t *)(m->windows[window].cpu+at)=v;return 0;}
static int mmio_barrier(void *cookie)
{(void)cookie;__asm__ volatile("dsb sy":::"memory");return 0;}
FuxiGmuStatus FuxiGmuBindMmio(FuxiGmuMmio *m,FuxiGmuIo *out)
{
    if(!out)return FuxiGmuArgument;
    *out=(FuxiGmuIo){0};
    if(!m)return FuxiGmuArgument;
    for(unsigned i=0;i<FuxiGmuWindows;++i) {
        const FuxiGmuMmioWindow *w=m->windows+i;
        if(!fits(m,i,0) || w->physical!=fuxi_gmu_window_physical[i] ||
            w->bytes!=fuxi_gmu_window_bytes[i])return FuxiGmuArgument;
        for(unsigned j=0;j<i;++j)if(overlap((uintptr_t)w->cpu,w->bytes,(uintptr_t)m->windows[j].cpu,m->windows[j].bytes))return FuxiGmuArgument;
    }
    out->cookie=m;out->read32=mmio_read;out->write32=mmio_write;out->barrier=mmio_barrier;
    for(unsigned i=0;i<FuxiGmuWindows;++i)out->bytes[i]=m->windows[i].bytes;
    return FuxiGmuSuccess;
}
