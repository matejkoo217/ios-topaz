/* SPDX-License-Identifier: MIT */
#ifndef SHENG_DPU_OBSERVATION_H
#define SHENG_DPU_OBSERVATION_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum {FuxiDpuMdssRegion=0,FuxiDpuMdpRegion=1,FuxiDpuObservationMaxAttempts=3};
typedef struct {
    void *cookie;
    size_t region_bytes[2];
    int (*read32)(void *,unsigned region,size_t offset,uint32_t *);
    uint64_t (*now_ns)(void *);
} FuxiDpuObservationIo;
typedef struct {
    uint32_t status,timing_enable,count_enable,command_trigger;
    uint32_t frame,line,hsync,vsync_period;
} FuxiDpuInterfaceObservation;
typedef struct {
    uint32_t mdp_version,mdss_version,mdss_irq_status,mdp_irq_enable,mdp_irq_status;
    /* Hardware interfaces 1 and 2 (DSI controllers 0 and 1); no master selected. */
    FuxiDpuInterfaceObservation interfaces[2];
    uint64_t began_ns,ended_ns;
    uint32_t active_mask,counters_enabled_mask,command_trigger_mask;
    uint32_t vsync_enabled_mask,vsync_pending_mask;
} FuxiDpuObservation;
typedef enum {
    FuxiDpuObservationComplete=0,FuxiDpuObservationArgument,
    FuxiDpuObservationIoError,FuxiDpuObservationClockError,FuxiDpuObservationUnstable
} FuxiDpuObservationStatus;
typedef struct {unsigned attempts,reads,failed_region;size_t failed_offset;} FuxiDpuObservationResult;
/* Read-only prerequisite instrument for the source-bound SM8550/DPU9 profile.
 * Caller owns the actual powered/clocks/resource mappings and serializes mode
 * changes throughout the call. Those are real platform leases, not booleans
 * this interface accepts as proof. CPU mappings must independently be native4K.
 * Complete means the bounded samples agree on configuration/frame counters.
 * It does NOT mean panel timing, master role, active native4K, IRQ routing or
 * presentation is qualified. Raw versions are observations, not reinterpreted
 * as identity proof. No writes, timer, sleep, IRQ enable or VBL/fence emission.
 * On any failure the observation remains zero; diagnostics describe the read.
 * The IO callbacks and output storage are disjoint, valid and single-owner. */
FuxiDpuObservationStatus FuxiDpuObserve(const FuxiDpuObservationIo *,FuxiDpuObservation *,FuxiDpuObservationResult *);
#ifdef __cplusplus
}
#endif
#endif
