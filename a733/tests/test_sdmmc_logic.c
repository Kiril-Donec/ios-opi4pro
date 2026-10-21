/*
 * Host test for the pure helpers of bsd/dev/a733_sdmmc.c. test_sdmmc_patch.py
 * extracts that file from a733/xnu-a733-sdmmc.patch and builds this test with
 * -DA733_SD_HOST_TEST -include <extracted a733_sdmmc.c>.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

#define CHECK(cond) do { \
	if (!(cond)) { \
		fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
		failures++; \
	} \
} while (0)

/* Set bits [lsb + width - 1 : lsb] of a 128-bit response, r[0] = bits 31:0. */
static void
setbits(uint32_t r[4], unsigned lsb, unsigned width, uint64_t value)
{
	for (unsigned i = 0; i < width; i++) {
		unsigned b = lsb + i;
		if (value & (1ull << i)) {
			r[b / 32] |= 1u << (b % 32);
		} else {
			r[b / 32] &= ~(1u << (b % 32));
		}
	}
}

static void
test_clock(void)
{
	/* gate | mux 1 (pll-peri0-400m) | N = 0 | M = 3: 100 MHz */
	CHECK(a733sd_ccu_mod_hz(0x81000003u) == 100000000ull);
	/* sys24M, no division */
	CHECK(a733sd_ccu_mod_hz(0x80000000u) == 24000000ull);
	/* pll-peri1-300m, M = 1, N = 2: 300 / 2 / 3 = 50 MHz */
	CHECK(a733sd_ccu_mod_hz(0x84000201u) == 50000000ull);
	CHECK(a733sd_ccu_mod_hz(0x01000003u) == 0);     /* gated */
	CHECK(a733sd_ccu_mod_hz(0x85000000u) == 0);     /* unknown parent */

	CHECK(a733sd_pick_div(100000000ull, 400000ull) == 125);
	CHECK(a733sd_card_hz_max(100000000ull, 125) == 400000ull);
	CHECK(a733sd_pick_div(100000000ull, 25000000ull) == 2);
	CHECK(a733sd_pick_div(24000000ull, 25000000ull) == 0);
	CHECK(a733sd_pick_div(24000000ull, 400000ull) == 30);
	CHECK(a733sd_pick_div(400000000ull, 400000ull) == 256);   /* does not fit */

	/* The chosen divider is the smallest one whose bound respects the limit. */
	static const uint64_t limits[] = { 400000ull, 25000000ull };
	for (uint64_t mod = 1000000ull; mod <= 408000000ull; mod += 997000ull) {
		for (unsigned l = 0; l < 2; l++) {
			uint32_t d = a733sd_pick_div(mod, limits[l]);
			if (d > 255) {
				CHECK(a733sd_card_hz_max(mod, 255) > limits[l]);
				continue;
			}
			CHECK(a733sd_card_hz_max(mod, d) <= limits[l]);
			if (d > 0) {
				CHECK(a733sd_card_hz_max(mod, d - 1) > limits[l]);
			}
		}
	}
}

static void
test_csd(void)
{
	uint32_t r[4] = { 0 };

	/* CSD 2.0; the owner's 64 GB card reports 61891149824 bytes. */
	setbits(r, 126, 2, 1);
	setbits(r, 48, 22, 61891149824ull / (512 * 1024) - 1);
	CHECK(a733sd_csd_sectors(r) * 512 == 61891149824ull);
	CHECK(a733sd_rbits(r, 48, 22) == 0x1cd1f);

	/* CSD 1.0, 2 GiB SDSC: READ_BL_LEN 10, C_SIZE 4095, C_SIZE_MULT 7 */
	memset(r, 0, sizeof(r));
	setbits(r, 126, 2, 0);
	setbits(r, 80, 4, 10);
	setbits(r, 62, 12, 4095);
	setbits(r, 47, 3, 7);
	CHECK(a733sd_csd_sectors(r) == 4194304ull);

	memset(r, 0, sizeof(r));
	setbits(r, 126, 2, 2);                          /* reserved structure */
	CHECK(a733sd_csd_sectors(r) == 0);

	/* CID product name bytes, as printed by sd_identify() */
	memset(r, 0, sizeof(r));
	const char *pnm = "SD64G";
	for (unsigned i = 0; i < 5; i++) {
		setbits(r, 96 - 8 * i, 8, (uint8_t)pnm[i]);
	}
	setbits(r, 120, 8, 0x03);
	for (unsigned i = 0; i < 5; i++) {
		CHECK(a733sd_rbits(r, 96 - 8 * i, 8) == (uint8_t)pnm[i]);
	}
	CHECK(a733sd_rbits(r, 120, 8) == 0x03);
}

static void
put32(uint8_t *p, uint32_t v)
{
	for (int i = 0; i < 4; i++) {
		p[i] = (uint8_t)(v >> (8 * i));
	}
}

static void
put64(uint8_t *p, uint64_t v)
{
	put32(p, (uint32_t)v);
	put32(p + 4, (uint32_t)(v >> 32));
}

static void
putbe32(uint8_t *p, uint32_t v)
{
	p[0] = (uint8_t)(v >> 24);
	p[1] = (uint8_t)(v >> 16);
	p[2] = (uint8_t)(v >> 8);
	p[3] = (uint8_t)v;
}

static void
test_mbr(void)
{
	uint8_t mbr[512] = { 0 };
	struct a733sd_part p;

	CHECK(a733sd_mbr_part(mbr, 2, &p) == EINVAL);
	mbr[510] = 0x55;
	mbr[511] = 0xaa;
	/* Current card: partition 1 at 32 MiB, 64 MiB (boot, ext4) */
	mbr[446 + 4] = 0x83;
	put32(mbr + 446 + 8, 65536);
	put32(mbr + 446 + 12, 131072);
	CHECK(a733sd_mbr_part(mbr, 2, &p) == ENOENT);
	CHECK(a733sd_mbr_part(mbr, 1, &p) == 0 && p.start == 65536 && p.count == 131072 && p.mbr_type == 0x83);
	/* Planned iOS root: partition 2 right after it, 16 GiB */
	mbr[462 + 4] = 0xaf;
	put32(mbr + 462 + 8, 196608);
	put32(mbr + 462 + 12, 33554432);
	CHECK(a733sd_mbr_part(mbr, 2, &p) == 0 && p.start == 196608 && p.count == 33554432 && p.mbr_type == 0xaf);
	CHECK(a733sd_mbr_part(mbr, 0, &p) == ENOENT);
	CHECK(a733sd_mbr_part(mbr, 5, &p) == ENOENT);
	mbr[478 + 4] = 0x05;                            /* extended */
	put32(mbr + 478 + 8, 40000000);
	put32(mbr + 478 + 12, 1000);
	CHECK(a733sd_mbr_part(mbr, 3, &p) == ENOENT);
	mbr[446 + 4] = 0xee;                            /* protective MBR */
	CHECK(a733sd_mbr_part(mbr, 2, &p) == EFTYPE);
}

static void
test_gpt(void)
{
	uint8_t hdr[512] = { 0 }, ent[128] = { 0 };
	uint64_t sector;
	uint32_t offset;
	struct a733sd_part p;

	CHECK(a733sd_gpt_locate(hdr, 1, &sector, &offset) == EINVAL);
	memcpy(hdr, "EFI PART", 8);
	put64(hdr + 72, 2);
	put32(hdr + 80, 128);
	put32(hdr + 84, 128);
	CHECK(a733sd_gpt_locate(hdr, 2, &sector, &offset) == 0 && sector == 2 && offset == 128);
	CHECK(a733sd_gpt_locate(hdr, 5, &sector, &offset) == 0 && sector == 3 && offset == 0);
	CHECK(a733sd_gpt_locate(hdr, 129, &sector, &offset) == ENOENT);
	put32(hdr + 84, 96);
	CHECK(a733sd_gpt_locate(hdr, 1, &sector, &offset) == EINVAL);

	CHECK(a733sd_gpt_entry(ent, &p) == ENOENT);
	ent[0] = 0x00; ent[1] = 0x53;                   /* any non-zero type GUID */
	put64(ent + 32, 196608);
	put64(ent + 40, 196608 + 33554432 - 1);
	const char *name = "iOS16";
	for (unsigned i = 0; name[i]; i++) {
		ent[56 + 2 * i] = (uint8_t)name[i];
	}
	CHECK(a733sd_gpt_entry(ent, &p) == 0 && p.start == 196608 && p.count == 33554432 &&
	    strcmp(p.name, "iOS16") == 0 && p.mbr_type == 0);
	put64(ent + 40, 100);
	CHECK(a733sd_gpt_entry(ent, &p) == EINVAL);
}

static void
test_hfs(void)
{
	uint8_t vh[512] = { 0 };
	struct a733sd_hfs h;
	uint64_t part = 33554432;                       /* 16 GiB in sectors */

	CHECK(a733sd_hfs_check(vh, part, &h) == EFTYPE);
	vh[0] = 'H'; vh[1] = '+';
	vh[3] = 4;
	putbe32(vh + 4, (1u << 8) | (1u << 13));
	putbe32(vh + 40, 4096);
	putbe32(vh + 44, 4194304);                      /* 16 GiB */
	CHECK(a733sd_hfs_check(vh, part, &h) == 0 && h.signature == 0x482b && h.version == 4 &&
	    h.block_size == 4096 && h.total_blocks == 4194304 && (h.attributes & (1u << 8)));
	CHECK(a733sd_hfs_check(vh, part - 1, &h) == EFBIG);
	vh[1] = 'X';
	CHECK(a733sd_hfs_check(vh, part, &h) == 0 && h.signature == 0x4858);
	putbe32(vh + 40, 3000);
	CHECK(a733sd_hfs_check(vh, part, &h) == EFTYPE);
	vh[0] = 'B'; vh[1] = 'D';
	putbe32(vh + 40, 4096);
	CHECK(a733sd_hfs_check(vh, part, &h) == EFTYPE && h.signature == 0x4244);
}

int
main(void)
{
	test_clock();
	test_csd();
	test_mbr();
	test_gpt();
	test_hfs();
	if (failures) {
		fprintf(stderr, "%d failure(s)\n", failures);
		return 1;
	}
	printf("PASS: A733 SD/MMC clock, CSD/CID, MBR/GPT and HFS+ helpers\n");
	return 0;
}
