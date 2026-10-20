/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "FuxiGmuCommandDb.h"
#include "FuxiGmuCommandDbSource.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do {if(!(x)){fprintf(stderr,"command-db line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
extern void source_db_fixture(uint8_t *,unsigned);
extern int source_db_lookup(uint8_t *,const char *,uint32_t *,size_t *,size_t *);
extern void source_db_corrupt(uint8_t *,unsigned);
static void compare(uint8_t *db,const char *name,uint32_t address,const FuxiGmuAux *aux)
{
    uint32_t expected;size_t offset,len;
    CHECK(!source_db_lookup(db,name,&expected,&offset,&len));
    if(address)CHECK(address==expected);
    if(aux)CHECK(aux->bytes==len && aux->data==db+offset);
}
void test_fuxi_command_db(AdrenoHfiStartupConfig *config)
{
    uint8_t *db=malloc(SHENG_GMU_COMMAND_DB_BYTES);CHECK(db);
    FuxiGmuVoteInputs in={.chip_id=0x43050a01,.enable_acd=1,.enable_ifpc=1};
    for(unsigned gmxc=0;gmxc<2;++gmxc) {
        source_db_fixture(db,gmxc);
        CHECK(FuxiGmuCommandDbInputs(db,SHENG_GMU_COMMAND_DB_BYTES,0x1234,&in)==FuxiGmuDbSuccess);
        CHECK(in.chip_id==0x43050a01 && in.enable_acd && in.enable_ifpc && in.gmxc_present==gmxc);
        compare(db,"gfx.lvl",0,&in.gfx);compare(db,"mx.lvl",0,&in.mx);compare(db,"cx.lvl",0,&in.cx);
        if(gmxc)compare(db,"gmxc.lvl",0,&in.gmxc);else CHECK(!in.gmxc.data && !in.gmxc.bytes);
        compare(db,"SH0",in.sh0.address,&in.sh0.aux);compare(db,"MC0",in.mc0.address,&in.mc0.aux);
        compare(db,"ACV",in.acv.address,&in.acv.aux);compare(db,"CN0",in.cn0_address,NULL);
        CHECK(FuxiGmuBuildStartup(&in,config)==AdrenoHfiStartupSuccess);
    }
    FuxiGmuVoteInputs before=in;
    for(size_t n=0;n<SHENG_GMU_COMMAND_DB_BYTES;++n) {
        CHECK(FuxiGmuCommandDbInputs(db,n,0x1234,&in)==FuxiGmuDbArgument);
        CHECK(!memcmp(&in,&before,sizeof(in)));
    }
    for(unsigned control=0;control<18;++control) {
        source_db_fixture(db,1);source_db_corrupt(db,control);
        FuxiGmuDbStatus status=FuxiGmuCommandDbInputs(db,SHENG_GMU_COMMAND_DB_BYTES,0x1234,&in);
        if(control==15 || control==16) {
            CHECK(status==FuxiGmuDbSuccess);
            AdrenoHfiStartupConfig prev=*config;
            CHECK(FuxiGmuBuildStartup(&in,config)==AdrenoHfiStartupInvalid && !memcmp(config,&prev,sizeof(prev)));
            in=before;
        } else {
            CHECK(status!=FuxiGmuDbSuccess && !memcmp(&in,&before,sizeof(in)));
            if(control==1)CHECK(status==FuxiGmuDbVersion);
            if(control==12)CHECK(status==FuxiGmuDbDuplicate);
            if(control==13)CHECK(status==FuxiGmuDbMissing);
        }
    }
    /* Bounded deterministic mutation sweep under ASan/UBSan. Never invoke
     * unsafe original lookup on malformed fixtures. */
    uint32_t rng=740;
    for(unsigned i=0;i<4096;++i) {
        source_db_fixture(db,1);rng=rng*1664525+1013904223;
        size_t at=rng%4096;db[at]^=(uint8_t)((rng>>16)|1);
        in=before;FuxiGmuDbStatus status=FuxiGmuCommandDbInputs(db,SHENG_GMU_COMMAND_DB_BYTES,0x1234,&in);
        if(status!=FuxiGmuDbSuccess)CHECK(!memcmp(&in,&before,sizeof(in)));
    }
    source_db_fixture(db,1);in=before;
    CHECK(!FuxiGmuCommandDbInputs(db,SHENG_GMU_COMMAND_DB_BYTES,0x1234,&in) && !FuxiGmuBuildStartup(&in,config));
    free(db);
    puts("PASS: original command-db struct/lookup oracle, both GMxC cases, every short reservation, 18 malformed controls and 4096 mutations; synthetic database only");
}
