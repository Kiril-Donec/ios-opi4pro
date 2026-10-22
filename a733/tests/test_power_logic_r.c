/*
 * Host test for the pure part of bsd/dev/a733_power.c after patch 9999r
 * (a733/xnu-a733-cpufreq-setup.patch): power button with the triple press,
 * the ported vendor cpufreq (efuse bin -> OPP column, row choice, AXP8191
 * voltage codes, PLL N), the THS formula and calibration, the thermal policy.
 * test_cpufreq_setup_patch.py builds it with -include and -DA733_POWER_HOST_TEST.
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
	struct pk_state s;
	memset(&s, 0, sizeof(s));

	/* Short press, hold chord as before. */
	events[0] = 0;
	CHECK(!pk_step(&s, true, false, 1000, rec));
	CHECK(!pk_step(&s, false, true, 1100, rec));
	CHECK(strcmp(events, "P+ P- ") == 0);
	events[0] = 0;
	memset(&s, 0, sizeof(s));
	pk_step(&s, true, false, 10000, rec);
	pk_step(&s, false, false, 10000 + PK_CHORD_MS, rec);
	pk_step(&s, false, true, 12000, rec);
	CHECK(strcmp(events, "P+ V+ V- P- ") == 0);

	/* Three short presses inside the window: true exactly on the third. */
	memset(&s, 0, sizeof(s));
	CHECK(!pk_step(&s, true, true, 20000, rec));
	CHECK(!pk_step(&s, true, true, 20400, rec));
	CHECK(pk_step(&s, true, true, 20800, rec));
	CHECK(!pk_step(&s, true, true, 21000, rec));            /* starts a new count */
	/* Too slow: no shutdown. */
	memset(&s, 0, sizeof(s));
	CHECK(!pk_step(&s, true, true, 30000, rec));
	CHECK(!pk_step(&s, true, true, 31000, rec));
	CHECK(!pk_step(&s, true, true, 31000 + PK_TRIPLE_MS, rec));
	/* A hold (power-off chord) in between resets the count. */
	memset(&s, 0, sizeof(s));
	CHECK(!pk_step(&s, true, true, 40000, rec));
	CHECK(!pk_step(&s, true, false, 40300, rec));
	CHECK(!pk_step(&s, false, false, 40300 + PK_CHORD_MS, rec));
	CHECK(!pk_step(&s, false, true, 42000, rec));
	CHECK(!pk_step(&s, true, true, 42200, rec));
	CHECK(s.clicks == 1);
}

static void
test_tables(void)
{
	const struct cf_opp *t[3] = { cf_a55, cf_a76, cf_dsu };
	unsigned n[3] = { CF_N(cf_a55), CF_N(cf_a76), CF_N(cf_dsu) };
	for (int k = 0; k < 3; k++) {
		for (unsigned i = 0; i < n[k]; i++) {
			if (i) {
				CHECK(t[k][i].mhz > t[k][i - 1].mhz);
			}
			for (int c = 0; c < CF_BINS; c++) {
				CHECK(t[k][i].mv[c] == 0 || (t[k][i].mv[c] >= 800 && t[k][i].mv[c] <= 1050));
			}
		}
	}
	/* Vendor rows (sun60iw2p1-cpu-vf.dtsi, 24 MHz): spot checks. */
	CHECK(cf_a76[CF_N(cf_a76) - 1].mhz == 1992 && cf_a76[CF_N(cf_a76) - 1].mv[0] == 1050);
	CHECK(cf_a55[CF_N(cf_a55) - 1].mhz == 1800 && cf_a55[CF_N(cf_a55) - 1].mv[8] == 900);
	CHECK(CF_N(cf_vf_map) == 11);
}

static void
test_bins(void)
{
	uint16_t idx;
	/* dvfs_ori in bits 15:8, dvfs_bak in 23:16 wins when non-zero. */
	CHECK(cf_column(0x00000400, &idx) == 4 && idx == 0x0400);
	CHECK(cf_column(0x00050400, &idx) == 5 && idx == 0x0500);
	CHECK(cf_column(0x00001400, &idx) == 7 && idx == 0x0401);
	CHECK(cf_column(0x00001100, &idx) == 1 && idx == 0x0101);   /* no own rows: base bin 0x0100 */
	CHECK(cf_column(0x00001200, &idx) == 2 && idx == 0x0201);
	CHECK(cf_column(0x0000ee00, &idx) == 1 && idx == 0x0100);   /* unknown code: vendor default */
	CHECK(cf_column(0x00000000, &idx) == 0 && idx == 0x0000);   /* blank efuse maps to vf0000, as Linux */
}

static void
test_pick(void)
{
	int col = 4;                                            /* vf0400 */
	int r = cf_pick(cf_a76, CF_N(cf_a76), col, 1050, 1008, 2256);
	CHECK(r >= 0 && cf_a76[r].mhz == 1992 && cf_a76[r].mv[col] == 1050);
	r = cf_pick(cf_a76, CF_N(cf_a76), col, 950, 1008, 2256);
	CHECK(r >= 0 && cf_a76[r].mhz == 1800 && cf_a76[r].mv[col] == 920);
	r = cf_pick(cf_a76, CF_N(cf_a76), col, 800, 1008, 2256);
	CHECK(r >= 0 && cf_a76[r].mhz == 1392);                 /* 1512 needs 820 mV on vf0400 */
	r = cf_pick(cf_a55, CF_N(cf_a55), 3, 1050, 1008, 2256);  /* vf0300 */
	CHECK(r >= 0 && cf_a55[r].mhz == 1392);
	/* Every column reaches at least 1200 MHz on the A76 at 800 mV, and the floor exists. */
	for (int c = 0; c < CF_BINS; c++) {
		r = cf_pick(cf_a76, CF_N(cf_a76), c, 800, 1008, 2256);
		CHECK(r >= 0 && cf_a76[r].mhz >= 1200);
		CHECK(cf_pick(cf_a76, CF_N(cf_a76), c, 1050, 1008, 1008) >= 0);
		CHECK(cf_pick(cf_a55, CF_N(cf_a55), c, 1050, 1008, 1008) >= 0);
		CHECK(cf_pick(cf_dsu, CF_N(cf_dsu), c, 1050, 672, 2256) >= 0);
	}
	/* Steps skip rows that are not for this bin and stop at the limits. */
	int top = cf_pick(cf_a76, CF_N(cf_a76), col, 1050, 1008, 2256);
	int down = cf_step(cf_a76, CF_N(cf_a76), col, top, -1, 1008, top);
	CHECK(cf_a76[down].mhz == 1944);
	CHECK(cf_step(cf_a76, CF_N(cf_a76), col, down, 1, 1008, top) == top);
	CHECK(cf_step(cf_a76, CF_N(cf_a76), col, top, 1, 1008, top) == top);
	int floor = cf_pick(cf_a76, CF_N(cf_a76), col, 1050, 1008, 1008);
	CHECK(cf_step(cf_a76, CF_N(cf_a76), col, floor, -1, 1008, top) == floor);
}

static void
test_codes(void)
{
	CHECK(cf_mv_code(800) == 30 && cf_code_mv(30) == 800);
	CHECK(cf_mv_code(1050) == 55 && cf_code_mv(55) == 1050);
	CHECK(cf_mv_code(1200) == 0x46 && cf_code_mv(0x46) == 1200);
	CHECK(cf_code_mv(0x47) == 1220 && cf_mv_code(1220) == 0x47);
	for (uint16_t mv = 500; mv <= 1200; mv += 10) {
		CHECK(cf_code_mv(cf_mv_code(mv)) == mv);
	}
	CHECK(cf_pll_n(936) == 39 && cf_pll_n(1992) == 83 && cf_pll_n(1008) == 42 && cf_pll_n(720) == 30);
	CHECK(cf_pll_n(408) == 0 && cf_pll_n(1000) == 0 && cf_pll_n(2280) == 0);
	for (unsigned i = 0; i < CF_N(cf_a76); i++) {
		CHECK(cf_a76[i].mhz < 672 || cf_pll_n(cf_a76[i].mhz) != 0);
	}
	for (unsigned i = 0; i < CF_N(cf_dsu); i++) {
		CHECK(cf_dsu[i].mhz < 672 || cf_pll_n(cf_dsu[i].mhz) != 0);
	}
}

static void
test_thermal(void)
{
	CHECK(ths_mc(2000) == (2000 - 2822) * -62);             /* ~51 C */
	CHECK(ths_mc(1700) == (1700 - 2835) * -59);
	CHECK(ths_mc(2000) > 40000 && ths_mc(2000) < 60000);
	/* Calibration: no factory temperature -> none; else a 12-bit code near 0x800. */
	uint32_t cal0[3] = { 0, 0, 0 }, cdata = 0;
	CHECK(ths_calib(cal0, 0, &cdata) != 0);
	/* factory 51.0 C, every sensor code 0x7d0 (~51 C): calibration ~0x800 */
	uint32_t cal[3] = { 0xd07d0000u | 510u, 0x07d07d07u, 0x7du };
	for (unsigned i = 0; i < 5; i++) {
		CHECK(ths_calib(cal, i, &cdata) == 0 && cdata <= 0xfff && cdata > 0x700 && cdata < 0x900);
	}
	CHECK(ths_calib(cal, 5, &cdata) != 0);
	CHECK(cf_thermal_action(50000) == CF_UP);
	CHECK(cf_thermal_action(85000) == CF_HOLD);
	CHECK(cf_thermal_action(91000) == CF_DOWN);
	CHECK(cf_thermal_action(106000) == CF_FLOOR);
}

int
main(void)
{
	test_button();
	test_tables();
	test_bins();
	test_pick();
	test_codes();
	test_thermal();
	if (failures) {
		printf("FAIL (%d)\n", failures);
		return 1;
	}
	printf("A733 power + cpufreq logic: PASS\n");
	return 0;
}
