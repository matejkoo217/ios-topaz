// SPDX-License-Identifier: MIT
// Board-side original PMGR ABI qualification. Default off. Modes: 1 releases
// unpublished objects, 2 publishes the original nub, 3 tests power refusal.
// No clocks, sleep, reset or secondary-CPU success is advertised.
#include "OriginalPMGRABI.h"
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <libkern/c++/OSSymbol.h>
#include <mach/kmod.h>
#include <pexpert/pexpert.h>

extern "C" {
extern kmod_info_t g_kernel_kmod_info;
kern_return_t OSKextLoadKextWithIdentifier(const char *);
void fuxi_pmgr_static_init(void) __asm__("__GLOBAL__sub_I_FuxiPlatformPower.cpp");
IOService *fuxi_original_pmgr_nub_create(IORegistryEntry *, ApplePMGR *);
uint32_t fuxi_original_pmgr_nub_read(IOService *);
void fuxi_original_pmgr_nub_write(IOService *, uint64_t);
// stage,status,parent-size,own-size,provider,nub,bound-provider,read-before,
// read-after,own-before,own-after,nub-before,nub-after,attached,registered,mode.
volatile uint64_t fuxi_pmgr_observation[16];
__attribute__((noinline)) void fuxi_pmgr_checkpoint(void) { __asm__ volatile("" ::: "memory"); }
}

__attribute__((noreturn)) static void unavailable(unsigned slot)
{
  fuxi_pmgr_observation[0] = 0x100 + slot;
  fuxi_pmgr_observation[1] = static_cast<uint32_t>(kIOReturnUnsupported);
  fuxi_pmgr_checkpoint();
  panic("FuxiPlatformPower: unimplemented operation %u", slot);
}

class FuxiPlatformPower : public ApplePMGR {
  OSDeclareDefaultStructors(FuxiPlatformPower)
public:
  void enableCPUCore(unsigned, uint64_t) override { unavailable(168); }
  void enableCPUCore(unsigned) override { unavailable(169); }
  void disableCPUCore(unsigned) override { unavailable(170); }
  void enableCPUCluster(unsigned) override { unavailable(171); }
  void disableCPUCluster(unsigned) override { unavailable(172); }
  void initCPUIdle(ml_processor_info_t *) override { unavailable(173); }
  void enterCPUIdle(UInt64 *) override { unavailable(174); }
  void exitCPUIdle(UInt64 *) override { unavailable(175); }
  void updateCPUIdle(UInt64 *) override { unavailable(176); }
#include "GuardedPMGRSlots.inc"
};
OSDefineMetaClassWithInit(FuxiPlatformPower, ApplePMGR, )
OSMetaClassConstructorInit(FuxiPlatformPower, ApplePMGR, )
OSDefineBasicStructors(FuxiPlatformPower, ApplePMGR)
// The original object's storage exceeds kalloc_type's 16 KiB size limit.
// Use XNU's existing zeroed, size-aware OSObject heap allocation pair.
void *FuxiPlatformPower::operator new(size_t size) { return OSObject::operator new(size); }
void FuxiPlatformPower::operator delete(void *memory, size_t size)
{
  OSObject::operator delete(memory, size);
}
static_assert(sizeof(FuxiPlatformPower) == 0x4b8a8, "Exact original provider storage");

static const OSMetaClass *lookup(const char *text)
{
  const OSSymbol *name = OSSymbol::withCString(text);
  const OSMetaClass *meta = name ? OSMetaClass::getMetaClassWithName(name) : nullptr;
  OSSafeReleaseNULL(name);
  return meta;
}

extern "C" void fuxi_pmgr_run(void)
{
  unsigned mode = 0;
  if (!PE_parse_boot_argn("fuxi-pmgr", &mode, sizeof(mode)) || !mode) return;
  fuxi_pmgr_observation[15] = mode;
  fuxi_pmgr_observation[1] = static_cast<uint32_t>(kIOReturnError);
  if (mode > 3 || fuxi_pmgr_observation[0]) { fuxi_pmgr_checkpoint(); return; }
  fuxi_pmgr_observation[0] = 1;
  kern_return_t result = OSKextLoadKextWithIdentifier("com.apple.driver.ApplePMGR");
  if (result) { fuxi_pmgr_observation[1] = static_cast<uint32_t>(result); fuxi_pmgr_checkpoint(); return; }
  const OSMetaClass *parent = lookup("ApplePMGR"), *nubMeta = lookup("ApplePMGRNub");
  if (!parent || parent != &ApplePMGR::gMetaClass || parent->getClassSize() != 0x4b8a8 ||
      !nubMeta || nubMeta->getClassSize() != 0x740) { fuxi_pmgr_checkpoint(); return; }
  fuxi_pmgr_observation[2] = parent->getClassSize();
  void *handle = OSMetaClass::preModLoad(g_kernel_kmod_info.name);
  if (!handle) { fuxi_pmgr_checkpoint(); return; }
  fuxi_pmgr_static_init();
  result = OSMetaClass::postModLoad(handle);
  if (result) { fuxi_pmgr_observation[1] = static_cast<uint32_t>(result); fuxi_pmgr_checkpoint(); return; }
  fuxi_pmgr_observation[9] = FuxiPlatformPower::gMetaClass.getInstanceCount();
  fuxi_pmgr_observation[11] = nubMeta->getInstanceCount();
  FuxiPlatformPower *provider = new FuxiPlatformPower;
  IORegistryEntry *description = new IORegistryEntry;
  IOService *nub = nullptr;
  do {
    if (!provider || !description || !provider->init() || !description->init()) break;
    fuxi_pmgr_observation[0] = 2;
    fuxi_pmgr_observation[3] = provider->getMetaClass()->getClassSize();
    fuxi_pmgr_observation[4] = reinterpret_cast<uintptr_t>(provider);
    // Empty resource description: no Apple register map or device capabilities.
    description->setName("fuxi-platform-power");
    nub = fuxi_original_pmgr_nub_create(description, provider);
    fuxi_pmgr_observation[5] = reinterpret_cast<uintptr_t>(nub);
    if (!nub || nub->getMetaClass() != nubMeta || !provider->metaCast("ApplePMGR")) break;
    uintptr_t bound = 0;
    memcpy(&bound, reinterpret_cast<const char *>(nub) + 0x88, sizeof(bound));
    fuxi_pmgr_observation[6] = bound;
    if (bound != reinterpret_cast<uintptr_t>(provider)) break;
    fuxi_pmgr_observation[0] = 3;
    uint32_t value = fuxi_original_pmgr_nub_read(nub);
    fuxi_pmgr_observation[7] = value;
    fuxi_original_pmgr_nub_write(nub, uint64_t(value | 4));
    fuxi_pmgr_observation[8] = fuxi_original_pmgr_nub_read(nub);
    fuxi_pmgr_observation[13] = nub->getProvider() != nullptr || provider->getProvider() != nullptr;
    fuxi_pmgr_observation[14] = (nub->getState() | provider->getState()) & kIOServiceRegisteredState;
    if (value != 0xffffffff || fuxi_pmgr_observation[8] != 0xffffffff ||
        fuxi_pmgr_observation[13] || fuxi_pmgr_observation[14]) break;
    if (mode == 3) provider->disableCPUCore(1);
    if (mode == 2) {
      IOService *platform = IOService::getPlatform();
      if (!platform || !provider->attach(platform)) break;
      if (!provider->start(platform)) { provider->detach(platform); break; }
      if (!nub->attach(provider)) {
        provider->stop(platform); provider->detach(platform); break;
      }
      if (!nub->start(provider)) {
        nub->detach(provider); provider->stop(platform); provider->detach(platform); break;
      }
      provider->registerService(kIOServiceSynchronous);
      nub->registerService(kIOServiceSynchronous);
      fuxi_pmgr_observation[0] = 5;
      fuxi_pmgr_observation[13] = nub->getProvider() == provider && provider->getProvider() == platform;
      fuxi_pmgr_observation[14] = (nub->getState() & provider->getState()) & kIOServiceRegisteredState;
      auto matching = IOService::serviceMatching("ApplePMGRNub");
      IOService *matched = matching ? IOService::waitForMatchingService(matching, 1000000) : nullptr;
      OSSafeReleaseNULL(matching);
      // Check actual service discovery and genuine type identity, then retain
      // both live objects. The registry and original nub refer to this provider.
      if (matched != nub || matched->getMetaClass() != nubMeta ||
          !fuxi_pmgr_observation[13] || !fuxi_pmgr_observation[14]) {
        fuxi_pmgr_checkpoint();
        panic("FuxiPlatformPower: original nub publication failed");
      }
      fuxi_pmgr_observation[10] = FuxiPlatformPower::gMetaClass.getInstanceCount();
      fuxi_pmgr_observation[12] = nubMeta->getInstanceCount();
      fuxi_pmgr_observation[1] = kIOReturnSuccess;
      OSSafeReleaseNULL(matched);
      OSSafeReleaseNULL(description);
      fuxi_pmgr_checkpoint();
      return;
    }
    fuxi_pmgr_observation[1] = kIOReturnSuccess;
  } while (false);
  OSSafeReleaseNULL(nub);
  OSSafeReleaseNULL(description);
  OSSafeReleaseNULL(provider);
  fuxi_pmgr_observation[10] = FuxiPlatformPower::gMetaClass.getInstanceCount();
  fuxi_pmgr_observation[12] = nubMeta->getInstanceCount();
  if (fuxi_pmgr_observation[9] != fuxi_pmgr_observation[10] ||
      fuxi_pmgr_observation[11] != fuxi_pmgr_observation[12]) fuxi_pmgr_observation[1] = static_cast<uint32_t>(kIOReturnError);
  fuxi_pmgr_observation[0] = 4;
  fuxi_pmgr_checkpoint();
}
