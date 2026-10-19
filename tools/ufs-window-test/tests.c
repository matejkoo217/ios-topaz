
/* ---- model of the strategy call's read path ---------------------------- */
static int
model_read(struct ufs_slot *slot, uint64_t off, uint32_t count, uint8_t *out)
{
	for (uint32_t done = 0; done < count;) {
		uint64_t pos = off + done;
		uint64_t lba = pos / UFS_BLOCK;
		uint32_t skip = (uint32_t)(pos % UFS_BLOCK);
		uint32_t want = MIN(count - done, BOUNCE_SIZE - skip);
		uint32_t blocks = (skip + want + UFS_BLOCK - 1) / UFS_BLOCK;
		const void *rbuf = NULL;
		int error = ufs_read_blocks_clustered(slot, su.first_block + lba, blocks,
		    &rbuf, count < (64u << 10));
		if (error) {
			return error;
		}
		memcpy(out + done, (const char *)rbuf + skip, want);
		done += want;
	}
	return 0;
}

/* Mirror of ufs_write_blocks_slot: fence, direct DMA write, seq bump. */
static int
model_write(struct ufs_slot *slot, uint64_t off, uint32_t count, const uint8_t *in)
{
	uint64_t lba = su.first_block + off / UFS_BLOCK;
	uint32_t skip = (uint32_t)(off % UFS_BLOCK);
	uint32_t blocks = (skip + count + UFS_BLOCK - 1) / UFS_BLOCK;

	if (off + count > su.nblocks * UFS_BLOCK) {
		return EPERM;
	}
	if (lba < su.first_block || lba + blocks > su.first_block + su.nblocks) {
		return EPERM;
	}
	if (skip || (count % UFS_BLOCK)) {          /* read-merge-write, as the driver does */
		if (ufs_read_blocks_slot(slot, su.first_block + lba, blocks)) {
			return EIO;
		}
	}
	memcpy((char *)slot_bounce(slot) + skip, in, count);
	memcpy(dev + lba * UFS_BLOCK, slot_bounce(slot),
	    (size_t)blocks * UFS_BLOCK);
	slot->win_blocks = 0;
	su.write_seq++;                             /* what os_atomic_inc_orig does */
	dev_writes++;
	return 0;
}

static void
reset_stats(void)
{
	dev_reads = 0;
	dev_blocks_read = 0;
	dev_reads_outside = 0;
}

static void
setup(uint64_t first, uint64_t nblocks, uint32_t ra_kib)
{
	memset(&su, 0, sizeof(su));
	su.first_block = first;
	su.nblocks = nblocks;
	su.ra_blocks = ra_kib ? (ra_kib << 10) / UFS_BLOCK : 0;
	for (int i = 0; i < 8; i++) {
		su.slot[i].index = i;
	}
	for (uint64_t b = 0; b < DEV_BLOCKS; b++) {
		for (uint32_t i = 0; i < UFS_BLOCK; i++) {
			dev[b * UFS_BLOCK + i] = (uint8_t)(b * 31 + i * 7 + (i >> 8));
		}
	}
	reset_stats();
}

static int failures;

#define CHECK(cond, ...) do { \
	if (!(cond)) { failures++; printf("FAIL: "); printf(__VA_ARGS__); printf("\n"); } \
} while (0)

int
main(void)
{
	static uint8_t out[4u << 20];
	static uint8_t expect[4u << 20];

	/* 1. cold sequential 4 KiB reads over 256 KiB, partition base 1000 */
	setup(1000, 3000, 256);
	long before = dev_reads;
	for (uint32_t r = 0; r < 64; r++) {
		CHECK(model_read(&su.slot[0], (uint64_t)r * 4096, 4096, out) == 0, "read %u", r);
		memcpy(expect, dev + 1000 * UFS_BLOCK + (uint64_t)r * 4096, 4096);
		CHECK(memcmp(out, expect, 4096) == 0, "data mismatch at read %u", r);
	}
	printf("1. 64 x 4 KiB sequential over 256 KiB: %ld commands (%.1f per read), %.2f MiB read\n",
	    dev_reads - before, (double)(dev_reads - before) / 64,
	    (double)dev_blocks_read * UFS_BLOCK / (1 << 20));
	CHECK(dev_reads - before <= 3, "expected <=3 commands for 256 KiB, got %ld", dev_reads - before);
	CHECK(dev_reads_outside == 0, "reads outside the partition");

	/* 2. random 4 KiB reads over the whole partition, with a second slot active */
	setup(1000, 3000, 256);
	for (int i = 0; i < 4000; i++) {
		uint32_t r = (uint32_t)(rng() % 3000);
		struct ufs_slot *slot = &su.slot[r % 2];
		CHECK(model_read(slot, (uint64_t)r * 4096, 4096, out) == 0, "rand read %u", r);
		CHECK(memcmp(out, dev + (1000 + r) * UFS_BLOCK, 4096) == 0, "rand data at %u", r);
	}
	printf("2. 4000 random 4 KiB reads, 2 slots: %ld commands, %ld reads outside\n",
	    dev_reads, dev_reads_outside);
	CHECK(dev_reads_outside == 0, "reads outside the partition");

	/* 3. write through another slot invalidates the window: no stale data */
	setup(1000, 3000, 256);
	CHECK(model_read(&su.slot[0], 0, 4096, out) == 0, "prime");
	uint8_t patch[4096];
	memset(patch, 0xa5, sizeof(patch));
	CHECK(model_write(&su.slot[1], 8 * 4096, 4096, patch) == 0, "write");
	CHECK(model_read(&su.slot[0], 8 * 4096, 4096, out) == 0, "re-read");
	CHECK(memcmp(out, patch, 4096) == 0, "slot 0 served a STALE window after a write via slot 1");
	memcpy(expect, dev + (1000 + 8) * UFS_BLOCK, 4096);
	CHECK(memcmp(out, expect, 4096) == 0, "re-read data");
	printf("3. window invalidated across slots by write: %s\n", failures ? "FAIL" : "ok");

	/* 4. partition end: last blocks, no read may cross the end */
	setup(1000, 100, 256);                      /* 100-block partition, window 64 */
	CHECK(model_read(&su.slot[0], 96 * 4096, 4 * 4096, out) == 0, "tail read");
	CHECK(memcmp(out, dev + (1000 + 96) * UFS_BLOCK, 4 * 4096) == 0, "tail data");
	CHECK(dev_reads_outside == 0, "tail read went outside the partition (%ld)", dev_reads_outside);
	CHECK(model_read(&su.slot[0], 0, 4096, out) == 0, "head read");
	CHECK(memcmp(out, dev + 1000 * UFS_BLOCK, 4096) == 0, "head data");
	CHECK(model_read(&su.slot[0], 99 * 4096, 4096, out) == 0, "last block");
	CHECK(dev_reads_outside == 0, "last-block read went outside the partition");
	/* reading past the end must still be refused by the fence, not by the window */
	CHECK(model_write(&su.slot[0], 100 * 4096, 4096, patch) == EPERM, "write past end was allowed");
	printf("4. partition clamping at head/tail: %ld reads, %ld outside\n",
	    dev_reads, dev_reads_outside);

	/* 5. ufsra=0: one command per read, the A/B baseline */
	setup(1000, 3000, 0);
	for (uint32_t r = 0; r < 64; r++) {
		CHECK(model_read(&su.slot[0], (uint64_t)r * 4096, 4096, out) == 0, "ra0 read %u", r);
	}
	printf("5. ufsra=0, 64 x 4 KiB: %ld commands (expect 64)\n", dev_reads);
	CHECK(dev_reads == 64, "ufsra=0 issued %ld commands, expected 64", dev_reads);

	/* 6. misaligned offsets and multi-block sizes, data checked against the device */
	setup(777, 2500, 256);
	for (int i = 0; i < 2000; i++) {
		uint32_t len = 512u + (uint32_t)(rng() % 60000);
		uint64_t off = rng() % ((uint64_t)2500 * 4096 - len);
		if (model_read(&su.slot[i % 4], off, len, out) != 0) {
			CHECK(0, "misaligned read failed at off %llu len %u",
			    (unsigned long long)off, len);
			continue;
		}
		memcpy(expect, dev + 777 * UFS_BLOCK + off, len);
		if (memcmp(out, expect, len) != 0) {
			uint32_t b = 0;
			while (out[b] == expect[b]) b++;
			printf("DBG out[0..3]=%02x %02x %02x %02x expect=%02x %02x %02x %02x (block %llu starts %02x)\n",
			    out[0], out[1], out[2], out[3], expect[0], expect[1], expect[2], expect[3],
			    (unsigned long long)((off+b)/4096), dev[((777+((off+b)/4096))*4096)]);
			printf("DBG off=%llu len=%u slot=%d badbyte=%u partblk=%llu skip=%llu win=%llu+%u win_seq=%llu seq=%llu\n",
			    (unsigned long long)off, len, i % 4, b,
			    (unsigned long long)((off + b) / 4096), (unsigned long long)((off + b) % 4096),
			    (unsigned long long)su.slot[i%4].win_lba, su.slot[i%4].win_blocks,
			    (unsigned long long)su.slot[i%4].win_seq, (unsigned long long)su.write_seq);
			failures++;
		}
	}
	printf("6. 2000 misaligned/random-size reads: %ld commands, %ld outside\n",
	    dev_reads, dev_reads_outside);
	CHECK(dev_reads_outside == 0, "misaligned reads went outside the partition");

	/* 7. reads larger than the window bypass it and stay correct */
	setup(1000, 3000, 256);
	before = dev_reads;
	CHECK(model_read(&su.slot[0], 0, 1u << 20, out) == 0, "1 MiB read");
	memcpy(expect, dev + 1000 * UFS_BLOCK, 1u << 20);
	CHECK(memcmp(out, expect, 1u << 20) == 0, "1 MiB data");
	printf("7. 1 MiB read: %ld commands\n", dev_reads - before);
	CHECK(dev_reads - before == 1, "1 MiB read took %ld commands", dev_reads - before);

	/* 8. sequential 64 KiB reads: 4x fewer commands expected */
	setup(1000, 3000, 256);
	before = dev_reads;
	for (uint32_t r = 0; r < 16; r++) {
		CHECK(model_read(&su.slot[0], (uint64_t)r * 65536, 65536, out) == 0, "64k read %u", r);
		memcpy(expect, dev + 1000 * UFS_BLOCK + (uint64_t)r * 65536, 65536);
		CHECK(memcmp(out, expect, 65536) == 0, "64 KiB data at %u", r);
	}
	printf("8. 16 x 64 KiB sequential: %ld commands (window off for >=64 KiB by design)\n",
	    dev_reads - before);

	printf("\n%s (%d failures)\n", failures ? "FAILURES" : "ALL CHECKS PASSED", failures);
	return failures ? 1 : 0;
}
