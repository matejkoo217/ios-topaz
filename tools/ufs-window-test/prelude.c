/*
 * Host-side test of the read-clustering logic: the EXACT function text from
 * bsd/dev/fuxi_ufs.c (extracted mechanically into window_extract.c) compiled
 * against stubs for the kernel pieces it calls.
 *
 * The point is not to test the UFS host controller -- that needs the phone --
 * but to show the window bookkeeping cannot return wrong bytes and cannot read
 * outside the partition, the two ways this feature could corrupt a root
 * filesystem.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>

#define UFS_BLOCK   4096u
#define BOUNCE_SIZE (1u << 20)
#define ENOENT 2
#define EINVAL 22
#define EIO 5
#define EPERM 1
#define ETIMEDOUT 60

#define MIN(a, b) ((a) < (b) ? (a) : (b))

static inline uint64_t
os_atomic_load_stub(const void *p)
{
	return *(const uint64_t *)p;
}
#define os_atomic_load(p, m) os_atomic_load_stub(p)

struct ufs_slot {
	uint32_t index;
	uint32_t tag;
	bool     busy;
	int      wait_chan;
	uint64_t win_lba;
	uint32_t win_blocks;
	uint64_t win_seq;
};

static struct {
	uint64_t first_block, nblocks;
	uint32_t ra_blocks;
	uint64_t write_seq;
	struct ufs_slot slot[8];
	uint8_t  buf[8][BOUNCE_SIZE];
} su;

static inline void *
slot_bounce(struct ufs_slot *slot)
{
	return su.buf[slot->index];
}

/* ---- fake device -------------------------------------------------------- */
#define DEV_BLOCKS 4096u
static uint8_t dev[DEV_BLOCKS * UFS_BLOCK];
static long dev_reads;                  /* number of SCSI read commands */
static long dev_blocks_read;
static long dev_reads_outside;          /* reads naming blocks outside [first, end) */
static bool dev_enforce_bounds = true;
static long dev_writes;

static uint64_t rng_state = 0x12345678;
static uint64_t
rng(void)
{
	rng_state ^= rng_state << 13;
	rng_state ^= rng_state >> 7;
	rng_state ^= rng_state << 17;
	return rng_state;
}

static int
ufs_read_blocks_slot(struct ufs_slot *slot, uint64_t lba, uint32_t count)
{
	uint64_t end = su.first_block + su.nblocks;

	if (lba > UINT32_MAX || count > BOUNCE_SIZE / UFS_BLOCK || count == 0) {
		return EINVAL;
	}
	if (dev_enforce_bounds &&
	    (lba < su.first_block || lba + count > end)) {
		dev_reads_outside++;
		return EPERM;
	}
	if (lba + count > DEV_BLOCKS) {
		return EINVAL;
	}
	/* mirrors ufs_scsi_slot: any data transfer through the bounce buffer
	 * drops the window, since the buffer IS the window */
	slot->win_blocks = 0;
	dev_reads++;
	dev_blocks_read += count;
	memcpy(slot_bounce(slot), dev + lba * UFS_BLOCK, (size_t)count * UFS_BLOCK);
	return 0;
}
