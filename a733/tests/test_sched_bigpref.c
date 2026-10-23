/*
 * Host test for the A733 big-core preference in choose_processor()
 * (a733/xnu-a733-sched-bigpref.patch, osfmk/kern/sched_prim.c).
 * test_sched_bigpref_patch.py cuts the SWEET block (sweet_big_cpus,
 * sweet_preferred) out of the patch into sched_block.inc; XNU types are
 * stubbed here. Topology as on the board: logical 0/1 = A76 (0x600/0x700),
 * 2..6 = A55 0x100..0x500 (cpus=7).
 */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define __improbable(x) (x)
#define BASEPRI_UTILITY         20
#define BASEPRI_DEFAULT         31
#define BASEPRI_USER_INITIATED  37
#define BASEPRI_FOREGROUND      47

typedef struct { unsigned int cpu_id; unsigned int phys_id; } ml_topology_cpu_t;
typedef struct { unsigned int num_cpus; ml_topology_cpu_t cpus[8]; } ml_topology_info_t;
struct thread { int sched_pri; };
typedef struct thread *thread_t;

static ml_topology_info_t topo;
static int bootarg = -1;
static const ml_topology_info_t *ml_get_topology_info(void) { return &topo; }
static bool
PE_parse_boot_argn(const char *name, void *out, int size)
{
	(void)size;
	if (bootarg >= 0 && strcmp(name, "a733bigpref") == 0) {
		*(int *)out = bootarg;
		return true;
	}
	return false;
}

#include "sched_block.inc"

static int failures;
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static void
board(unsigned int n, int arg)
{
	static const unsigned int phys[8] = { 0x600, 0x700, 0x100, 0x200, 0x300, 0x400, 0x500, 0x000 };
	topo.num_cpus = n;
	for (unsigned int i = 0; i < n; i++) {
		topo.cpus[i].cpu_id = i;
		topo.cpus[i].phys_id = phys[i];
	}
	bootarg = arg;
	sweet_big_pref = -1;                    /* re-read the topology */
	sweet_big_mask = 0;
}

int
main(void)
{
	struct thread ui = { BASEPRI_FOREGROUND }, ini = { BASEPRI_USER_INITIATED }, def = { BASEPRI_DEFAULT },
	    util = { BASEPRI_UTILITY }, bg = { 4 };

	board(7, -1);
	CHECK(sweet_big_cpus() == 0x3);
	uint64_t all = 0x7f;
	CHECK(sweet_preferred(&ui, all) == 0x3);            /* interactive: A76s */
	CHECK(sweet_preferred(&ini, all) == 0x3);
	CHECK(sweet_preferred(&def, all) == 0);             /* default QoS: unchanged */
	CHECK(sweet_preferred(&util, all) == 0x7c);         /* background: A55s */
	CHECK(sweet_preferred(&bg, all) == 0x7c);
	/* Only A55s idle: an interactive thread gets no preference (caller falls back). */
	CHECK(sweet_preferred(&ui, 0x7c) == 0);
	/* Only an A76 idle: background gets no preference, may still use it. */
	CHECK(sweet_preferred(&bg, 0x2) == 0);
	CHECK(sweet_preferred(&ui, 0x2) == 0x2);

	/* Only A76s online (cpus=2) or only one kind: no preference at all. */
	board(2, -1);
	CHECK(sweet_big_cpus() == 0);
	CHECK(sweet_preferred(&ui, 0x3) == 0 && sweet_preferred(&bg, 0x3) == 0);
	/* Boot-arg off. */
	board(7, 0);
	CHECK(sweet_big_cpus() == 0 && sweet_preferred(&ui, all) == 0);
	/* All 8 cores: 0x000 (logical 7) is an A55. */
	board(8, -1);
	CHECK(sweet_big_cpus() == 0x3 && sweet_preferred(&bg, 0xff) == 0xfc);

	if (failures) {
		printf("FAIL (%d)\n", failures);
		return 1;
	}
	printf("A733 big-core preference: PASS\n");
	return 0;
}
