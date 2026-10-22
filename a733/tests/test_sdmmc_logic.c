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

	/* Vendor 2x mode: card = module / 2 (div 0) or module / (4 div). */
	CHECK(a733sd_card_hz(100000000ull, 0) == 50000000ull);
	CHECK(a733sd_card_hz(100000000ull, 1) == 25000000ull);
	CHECK(a733sd_card_hz(100000000ull, 2) == 12500000ull);    /* the old transfer divider */
	CHECK(a733sd_pick_div(100000000ull, 400000ull) == 63);    /* 396825 Hz */
	CHECK(a733sd_card_hz(100000000ull, 63) <= 400000ull);
	CHECK(a733sd_pick_div(100000000ull, 25000000ull) == 1);   /* board: Default Speed 25 MHz */
	CHECK(a733sd_pick_div(100000000ull, 50000000ull) == 0);   /* board: High Speed 50 MHz */
	CHECK(a733sd_pick_div(24000000ull, 25000000ull) == 0);
	CHECK(a733sd_pick_div(24000000ull, 400000ull) == 15);
	CHECK(a733sd_pick_div(408000000ull, 400000ull) == 255);
	CHECK(a733sd_pick_div(420000000ull, 400000ull) == 256);   /* does not fit */

	/* The chosen divider is the smallest one whose card clock respects the limit. */
	static const uint64_t limits[] = { 400000ull, 25000000ull, 50000000ull };
	for (uint64_t mod = 1000000ull; mod <= 408000000ull; mod += 997000ull) {
		for (unsigned l = 0; l < 3; l++) {
			uint32_t d = a733sd_pick_div(mod, limits[l]);
			if (d > 255) {
				CHECK(a733sd_card_hz(mod, 255) > limits[l]);
				continue;
			}
			CHECK(a733sd_card_hz(mod, d) <= limits[l]);
			if (d > 0) {
				CHECK(a733sd_card_hz(mod, d - 1) > limits[l]);
			}
		}
	}

	/* CMD6 switch status: group 1 support (byte 13 bit 1) and selection (byte 16 low nibble). */
	uint8_t st[64] = { 0 };
	st[13] = 0x03;                                  /* functions 0 and 1 supported */
	st[16] = 0x01;
	CHECK(a733sd_cmd6_hs_supported(st) && a733sd_cmd6_group1(st) == 1);
	st[13] = 0x01;
	CHECK(!a733sd_cmd6_hs_supported(st));
	st[16] = 0x0f;                                  /* cannot switch */
	CHECK(a733sd_cmd6_group1(st) == 0x0f);
	st[16] = 0xf1;                                  /* group 2 nibble must not matter */
	CHECK(a733sd_cmd6_group1(st) == 1);
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

/* In-memory FAT32 volume: 1 sector per cluster, 2 FATs, root at cluster 2. */
#define VOL_CLUSTERS    70000u
#define VOL_RESERVED    32u
#define VOL_FATSZ       ((VOL_CLUSTERS + 2) * 4 / 512 + 1)
#define VOL_DATA        (VOL_RESERVED + 2 * VOL_FATSZ)
#define VOL_SECTORS     (VOL_DATA + VOL_CLUSTERS)

struct vol {
	uint8_t *img;
	uint64_t sectors;
	int reads;
};

static int
vol_read(void *ctx, uint64_t sector, uint8_t *buf)
{
	struct vol *v = ctx;
	v->reads++;
	if (sector >= v->sectors) {
		return EIO;
	}
	memcpy(buf, v->img + sector * 512, 512);
	return 0;
}

static void
vol_fat_set(struct vol *v, uint32_t cluster, uint32_t value)
{
	for (unsigned f = 0; f < 2; f++) {
		put32(v->img + (VOL_RESERVED + f * VOL_FATSZ) * 512 + cluster * 4, value);
	}
}

static uint8_t *
vol_cluster(struct vol *v, uint32_t cluster)
{
	return v->img + (VOL_DATA + cluster - 2) * 512;
}

static void
dirent(uint8_t *e, const char name[11], uint8_t attr, uint32_t cluster, uint32_t size)
{
	memcpy(e, name, 11);
	e[11] = attr;
	e[20] = (uint8_t)(cluster >> 16);
	e[21] = (uint8_t)(cluster >> 24);
	e[26] = (uint8_t)cluster;
	e[27] = (uint8_t)(cluster >> 8);
	put32(e + 28, size);
}

static void
vol_make(struct vol *v, uint32_t file_clusters)
{
	v->sectors = VOL_SECTORS;
	v->img = calloc(VOL_SECTORS, 512);
	if (!v->img) {
		abort();
	}
	uint8_t *bs = v->img;
	bs[0] = 0xeb; bs[1] = 0x58; bs[2] = 0x90;
	memcpy(bs + 3, "MSDOS5.0", 8);
	bs[11] = 0x00; bs[12] = 0x02;                   /* 512 bytes per sector */
	bs[13] = 1;                                     /* sectors per cluster */
	bs[14] = VOL_RESERVED; bs[15] = 0;
	bs[16] = 2;                                     /* FATs */
	bs[21] = 0xf8;
	put32(bs + 32, VOL_SECTORS);
	put32(bs + 36, VOL_FATSZ);
	put32(bs + 44, 2);                              /* root cluster */
	memcpy(bs + 82, "FAT32   ", 8);
	bs[510] = 0x55; bs[511] = 0xaa;
	vol_fat_set(v, 0, 0x0ffffff8);
	vol_fat_set(v, 1, 0x0fffffff);
	vol_fat_set(v, 2, 0x0fffffff);                  /* root: one cluster */
	uint8_t *root = vol_cluster(v, 2);
	dirent(root, "LOGS       ", 0x08, 0, 0);       /* volume label */
	root[32] = 0x41; root[32 + 11] = 0x0f;          /* long-name entry */
	dirent(root + 64, "OLDLOG  TXT", 0x20, 100, 4096);
	root[64] = 0xe5;                                /* deleted */
	dirent(root + 96, "A733LOG TXT", 0x20, 3, file_clusters * 512);
	for (uint32_t c = 3; c < 3 + file_clusters; c++) {
		vol_fat_set(v, c, c + 1 < 3 + file_clusters ? c + 1 : 0x0fffffff);
	}
	memcpy(vol_cluster(v, 3), "A733 first sector", 17);
}

static void
test_fat(void)
{
	struct vol v;
	struct a733sd_fat f;
	uint8_t sec[512];
	uint64_t first = 0;
	uint32_t size = 0, bad = 0;

	vol_make(&v, 1024);                             /* 512 KiB log file */
	CHECK(a733sd_fat32_parse(v.img, v.sectors, &f) == 0);
	CHECK(f.sectors_per_cluster == 1 && f.fat_start == VOL_RESERVED && f.data_start == VOL_DATA &&
	    f.root_cluster == 2 && f.clusters == VOL_CLUSTERS);
	CHECK(a733sd_fat32_parse(v.img, v.sectors - 1, &f) == EFTYPE);    /* larger than partition */

	CHECK(a733sd_fat_find_log(vol_read, &v, v.sectors, sec, &first, &size, &bad) == 0);
	CHECK(first == VOL_DATA + 1 && size == 1024 * 512 && bad == 0);
	CHECK(memcmp(v.img + first * 512, "A733 first sector", 17) == 0);

	/* The file entry in a second root directory cluster */
	uint8_t *root = vol_cluster(&v, 2);
	uint8_t entry[32];
	memcpy(entry, root + 96, 32);
	memset(root + 96, 0, 32);
	root[96] = 'X';                                 /* keep the directory going */
	memcpy(root + 96, "NOTES   TXT", 11);
	for (unsigned i = 4; i < 16; i++) {
		dirent(root + 32 * i, "FILLER  BIN", 0x20, 0, 0);
	}
	vol_fat_set(&v, 2, 5000);
	vol_fat_set(&v, 5000, 0x0fffffff);
	memcpy(vol_cluster(&v, 5000), entry, 32);
	CHECK(a733sd_fat_find_log(vol_read, &v, v.sectors, sec, &first, &size, &bad) == 0);
	CHECK(first == VOL_DATA + 1);

	/* Fragmented file: never written */
	vol_fat_set(&v, 500, 6000);
	CHECK(a733sd_fat_find_log(vol_read, &v, v.sectors, sec, &first, &size, &bad) == EINVAL && bad == 500);
	vol_fat_set(&v, 500, 501);
	/* Chain longer than the size says: last cluster must be end of chain */
	vol_fat_set(&v, 1026, 1027);
	CHECK(a733sd_fat_find_log(vol_read, &v, v.sectors, sec, &first, &size, &bad) == EINVAL && bad == 1026);
	vol_fat_set(&v, 1026, 0x0fffffff);
	CHECK(a733sd_fat_find_log(vol_read, &v, v.sectors, sec, &first, &size, &bad) == 0);

	/* Too small */
	put32(vol_cluster(&v, 5000) + 28, 64 * 1024);
	CHECK(a733sd_fat_find_log(vol_read, &v, v.sectors, sec, &first, &size, &bad) == EINVAL && bad == 0);
	put32(vol_cluster(&v, 5000) + 28, 1024 * 512);

	/* No file, then not FAT32 at all */
	vol_cluster(&v, 5000)[0] = 0xe5;
	CHECK(a733sd_fat_find_log(vol_read, &v, v.sectors, sec, &first, &size, &bad) == ENOENT);
	v.img[510] = 0;
	CHECK(a733sd_fat_find_log(vol_read, &v, v.sectors, sec, &first, &size, &bad) == ENODEV);
	free(v.img);

	/* Directory scan helper on its own */
	uint8_t d[512] = { 0 };
	dirent(d, "A733LOG TXT", 0x10, 9, 0);           /* a directory, not the file */
	CHECK(a733sd_fat_dir_find(d, &bad, &size) == ENOENT);
	memset(d, 0, sizeof(d));
	for (unsigned i = 0; i < 16; i++) {
		dirent(d + 32 * i, "OTHER   TXT", 0x20, 9, 1);
	}
	CHECK(a733sd_fat_dir_find(d, &bad, &size) == EAGAIN);
}

struct file_ctx {
	FILE *f;
	uint64_t base;
};

static int
file_read(void *ctx, uint64_t sector, uint8_t *buf)
{
	struct file_ctx *c = ctx;
	if (fseek(c->f, (long)((c->base + sector) * 512), SEEK_SET) != 0) {
		return EIO;
	}
	return fread(buf, 1, 512, c->f) == 512 ? 0 : EIO;
}

/*
 * test_sdmmc_logic IMAGE: find A733LOG.TXT with the driver's own code in a
 * FAT32 image made by mkfs.fat + mcopy; print where it starts.
 */
static int
image_mode(const char *path)
{
	struct file_ctx c = { fopen(path, "rb"), 0 };
	uint8_t sec[512], head[32];
	uint64_t first = 0;
	uint32_t size = 0, bad = 0;

	if (!c.f) {
		perror(path);
		return 2;
	}
	fseek(c.f, 0, SEEK_END);
	uint64_t sectors = (uint64_t)ftell(c.f) / 512;
	int error = a733sd_fat_find_log(file_read, &c, sectors, sec, &first, &size, &bad);
	if (error) {
		printf("ERROR %d bad_cluster %u\n", error, bad);
		return 1;
	}
	if (file_read(&c, first, sec) != 0) {
		return 1;
	}
	memcpy(head, sec, sizeof(head) - 1);
	head[sizeof(head) - 1] = 0;
	for (unsigned i = 0; i < sizeof(head) - 1; i++) {
		if (head[i] < 0x20 || head[i] > 0x7e) {
			head[i] = '.';
		}
	}
	printf("FOUND sector %llu size %u head \"%s\"\n", (unsigned long long)first, size, head);
	fclose(c.f);
	return 0;
}

int
main(int argc, char **argv)
{
	if (argc == 2) {
		return image_mode(argv[1]);
	}
	test_clock();
	test_csd();
	test_mbr();
	test_gpt();
	test_hfs();
	test_fat();
	if (failures) {
		fprintf(stderr, "%d failure(s)\n", failures);
		return 1;
	}
	printf("PASS: A733 SD/MMC clock, CSD/CID, MBR/GPT, HFS+ and FAT32 log-file helpers\n");
	return 0;
}
