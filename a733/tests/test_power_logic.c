/*
 * Host test for the pure part of bsd/dev/a733_power.c (patch 9999q): the
 * power-button state machine (short press, hold -> volume-up chord), the
 * R_TWI0 clock divider choice and the CPU PLL decoding.
 * test_cores_fb_power_patch.py builds it with -include and
 * -DA733_POWER_HOST_TEST.
 */
#include <stdio.h>
#include <string.h>

static int failures;
#define CHECK(cond) do { \
	if (!(cond)) { \
		fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
		failures++; \
	} \
} while (0)

static char events[256];

static void
rec(int key, int down)
{
	char e[8];
	snprintf(e, sizeof(e), "%c%c ", key == PK_POWER ? 'P' : 'V', down ? '+' : '-');
	strncat(events, e, sizeof(events) - strlen(events) - 1);
}

static void
test_button(void)
{
	struct pk_state s = { false, false, 0 };

	/* Short press over two polls: side button down, up. */
	events[0] = 0;
	pk_step(&s, true, false, 1000, rec);
	pk_step(&s, false, false, 1050, rec);
	pk_step(&s, false, true, 1200, rec);
	CHECK(strcmp(events, "P+ P- ") == 0);
	CHECK(!s.down);

	/* Press and release inside one poll: still a complete click. */
	events[0] = 0;
	pk_step(&s, true, true, 2000, rec);
	CHECK(strcmp(events, "P+ P- ") == 0);

	/* Held: volume up joins after PK_CHORD_MS (slide to power off), both released. */
	events[0] = 0;
	pk_step(&s, true, false, 3000, rec);
	for (uint64_t t = 3050; t < 3000 + PK_CHORD_MS; t += 50) {
		pk_step(&s, false, false, t, rec);
	}
	CHECK(strcmp(events, "P+ ") == 0);
	pk_step(&s, false, false, 3000 + PK_CHORD_MS, rec);
	CHECK(strcmp(events, "P+ V+ ") == 0);
	pk_step(&s, false, false, 3000 + PK_CHORD_MS + 500, rec);          /* only once */
	pk_step(&s, false, true, 6000, rec);
	CHECK(strcmp(events, "P+ V+ V- P- ") == 0);

	/* A stray release (missed press) does nothing; a second press while down is ignored. */
	events[0] = 0;
	pk_step(&s, false, true, 7000, rec);
	CHECK(events[0] == 0);
	pk_step(&s, true, false, 8000, rec);
	pk_step(&s, true, false, 8050, rec);
	pk_step(&s, false, true, 8100, rec);
	CHECK(strcmp(events, "P+ P- ") == 0);
}

static void
test_clocks(void)
{
	uint32_t hz;
	/* 24 MHz dcxo: the fastest setting not above 100 kHz. */
	uint32_t ccr = twi_ccr_for(24000000, 100000, &hz);
	CHECK(hz <= 100000 && hz >= 90000);
	CHECK(24000000 / (10u * (((ccr >> 3) & 0xf) + 1) << (ccr & 7)) == hz);
	/* 200 MHz peri0: still at or below 100 kHz. */
	ccr = twi_ccr_for(200000000, 100000, &hz);
	CHECK(hz <= 100000 && hz >= 75000);
	CHECK((ccr & ~0x7fu) == 0);
	/* Unreachably slow request: the slowest divider, never above the limit. */
	ccr = twi_ccr_for(200000000, 1000, &hz);
	CHECK(ccr == (7u | (15u << 3)) && hz < 100000);

	CHECK(r_apbs1_hz(0x00000000) == 24000000);              /* dcxo /1 */
	CHECK(r_apbs1_hz(0x03000001) == 100000000);             /* peri0-200m /2 */
	CHECK(r_apbs1_hz(0x04000000) == 24000000);              /* pll-ref */

	/* N = 0x53 (83) * 24 = 1992 MHz, P = 0; P = 1 halves it. */
	CHECK(cpu_pll_mhz(0x88005300u, 0x03000000u) == 1992);
	CHECK(cpu_pll_mhz(0x88005300u, 0x03010000u) == 996);
	CHECK(cpu_pll_mhz(0x88002a00u, 0x03000000u) == 1008);
}

int
main(void)
{
	test_button();
	test_clocks();
	if (failures) {
		printf("FAIL (%d)\n", failures);
		return 1;
	}
	printf("A733 power logic: PASS\n");
	return 0;
}
