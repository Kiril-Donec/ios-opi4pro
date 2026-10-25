/*
 * Host test of the pure parts of bsd/dev/a733_eth.c (a733/xnu-a733-eth.patch),
 * built with -DA733_ETH_HOST_TEST -include a733_eth.c: syscon value, PHY
 * link resolution, MAC from the chip ID, IPv4 checksum, DHCP frames.
 */
#include <stdio.h>

static int failures;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static void
test_syscon(void)
{
	/* Board DT: aw,tx-delay 12, aw,rx-delay 10, external TX clock (vendor value 0x11145). */
	CHECK(eth_syscon(12, 10, true) == 0x11145);
	CHECK(eth_syscon(0, 0, true) == 0x5);
	CHECK(eth_syscon(0, 0, false) == 0x6);
	CHECK(eth_syscon(31, 31, true) == (0x5u | (3u << 16) | (7u << 10) | (31u << 5)));
}

static void
test_yt8531(void)
{
	/* Linux motorcomm.c, 125 MHz from the PLL: enable bit 6 | 125M bit 4, source 0. */
	CHECK(yt8531_clkout(0x0000, true) == 0x0050);
	CHECK(yt8531_clkout(0x0000, false) == 0x0040);
	/* Other bits kept, old source / rate cleared. */
	CHECK(yt8531_clkout(0x810e, true) == 0x8150);
	CHECK(yt8531_clkout(0xffff, false) == (0xffff & ~0x5eu) + 0x40u);
	/* Variant 0 is the vendor setup; the test #17 setup is still in the list. */
	CHECK(eth_variants[0].clk_ext && eth_variants[0].phy125 && eth_variants[0].tx_delay == -1);
	bool saw_internal = false, saw_25m = false;
	for (unsigned i = 0; i < ETH_VARIANTS; i++) {
		saw_internal |= !eth_variants[i].clk_ext;
		saw_25m |= !eth_variants[i].phy125;
		CHECK(eth_variants[i].tx_delay >= -1 && eth_variants[i].tx_delay <= 31);
	}
	CHECK(saw_internal && saw_25m);
}

static void
test_lb_pick(void)
{
	static uint8_t g[LB_NT][LB_NR];
	unsigned t = 99, r = 99;
	memset(g, 0, sizeof(g));
	CHECK(!lb_pick(g, &t, &r));                             /* nothing passes */
	g[2][9] = LB_FRAMES;
	CHECK(lb_pick(g, &t, &r) && t == 2 && r == 9);          /* single point */
	g[2][9] = 3;
	CHECK(!lb_pick(g, &t, &r));                             /* partial is a failure */
	/* A 5x5 passing window at t 3..7, r 1..5: its centre (5, 3) is the farthest from failures. */
	memset(g, 0, sizeof(g));
	for (unsigned a = 3; a <= 7; a++) {
		for (unsigned b = 1; b <= 5; b++) {
			g[a][b] = LB_FRAMES;
		}
	}
	CHECK(lb_pick(g, &t, &r) && t == 5 && r == 3);
	/* Everything passes: the middle of the grid. */
	memset(g, LB_FRAMES, sizeof(g));
	CHECK(lb_pick(g, &t, &r) && t == (LB_NT - 1) / 2 && r == (LB_NR - 1) / 2);
	CHECK(LB_NT == 11 && LB_NR == 11 && lb_txd[LB_NT - 1] == 31 && lb_rxd[LB_NR - 1] == 31);
}

static void
test_phy(void)
{
	unsigned speed = 0;
	bool full = false;
	CHECK(!eth_phy_resolve(0x7809, 0x01e1, 0xcde1, 0x0300, 0x3800, &speed, &full));     /* no link */
	CHECK(eth_phy_resolve(0x782d, 0x01e1, 0xcde1, 0x0300, 0x3800, &speed, &full));
	CHECK(speed == 1000 && full);
	CHECK(eth_phy_resolve(0x782d, 0x01e1, 0xc5e1, 0x0300, 0x0000, &speed, &full));      /* 100 Mbit switch */
	CHECK(speed == 100 && full);
	CHECK(eth_phy_resolve(0x782d, 0x01e1, 0x40a1, 0x0300, 0x0000, &speed, &full));
	CHECK(speed == 100 && !full);
	CHECK(eth_phy_resolve(0x782d, 0x01e1, 0x4061, 0x0000, 0x0800, &speed, &full));      /* 1000 not advertised */
	CHECK(speed == 10 && full);
}

static void
test_mac(void)
{
	uint32_t a[4] = { 0x12345678, 0x9abcdef0, 0x0, 0x1 }, b[4] = { 0x12345678, 0x9abcdef0, 0x0, 0x2 };
	uint8_t m1[6], m2[6], m3[6];
	eth_mac_from_chipid(a, m1);
	eth_mac_from_chipid(a, m3);
	eth_mac_from_chipid(b, m2);
	CHECK(m1[0] == 0x02);                   /* locally administered unicast */
	CHECK(memcmp(m1, m3, 6) == 0);          /* stable */
	CHECK(memcmp(m1, m2, 6) != 0);          /* differs per chip */
}

static void
test_csum(void)
{
	/* RFC 1071 example header (Wikipedia "IPv4 header checksum"): checksum 0xb861. */
	uint8_t h[20] = { 0x45, 0x00, 0x00, 0x73, 0x00, 0x00, 0x40, 0x00, 0x40, 0x11, 0x00, 0x00,
		          0xc0, 0xa8, 0x00, 0x01, 0xc0, 0xa8, 0x00, 0xc7 };
	CHECK(ip_csum(h, 20) == 0xb861);
	h[10] = 0xb8;
	h[11] = 0x61;
	CHECK(ip_csum(h, 20) == 0);
}

/* Turn our own request into a server reply: op 2, yiaddr, options. */
static unsigned
make_reply(uint8_t *f, const uint8_t mac[6], uint32_t xid, int type)
{
	unsigned len = dhcp_build(f, mac, xid, DHCP_DISCOVER, 0, 0);
	uint8_t *ip = f + 14, *udp = ip + 20, *b = udp + 8;
	put16(udp, 67);
	put16(udp + 2, 68);
	b[0] = 2;
	put32(b + 16, 0xc0a8012a);              /* 192.168.1.42 */
	uint8_t *o = b + 240;
	*o++ = 53; *o++ = 1; *o++ = (uint8_t)type;
	*o++ = 54; *o++ = 4; put32(o, 0xc0a80101); o += 4;
	*o++ = 1; *o++ = 4; put32(o, 0xffffff00); o += 4;
	*o++ = 3; *o++ = 4; put32(o, 0xc0a80101); o += 4;
	*o++ = 51; *o++ = 4; put32(o, 86400); o += 4;
	*o++ = 0;                               /* pad */
	*o++ = 255;
	return len;
}

static void
test_dhcp(void)
{
	static uint8_t f[DHCP_FRAME_MAX];
	const uint8_t mac[6] = { 0x02, 0x11, 0x22, 0x33, 0x44, 0x55 };
	unsigned len = dhcp_build(f, mac, 0xdeadbeef, DHCP_DISCOVER, 0, 0);
	CHECK(len == 14 + 20 + 8 + 300);
	CHECK(len <= DHCP_FRAME_MAX);
	CHECK(f[0] == 0xff && f[5] == 0xff && memcmp(f + 6, mac, 6) == 0 && f[12] == 0x08 && f[13] == 0);
	CHECK(ip_csum(f + 14, 20) == 0);                        /* header checksum valid */
	CHECK(f[14 + 9] == 17 && get32(f + 14 + 16) == 0xffffffff);
	CHECK(f[14 + 20 + 1] == 68 && f[14 + 20 + 3] == 67);
	CHECK((unsigned)((f[14 + 2] << 8) | f[14 + 3]) == len - 14);
	CHECK((unsigned)((f[14 + 20 + 4] << 8) | f[14 + 20 + 5]) == len - 14 - 20);
	const uint8_t *b = f + 42;
	CHECK(b[0] == 1 && get32(b + 4) == 0xdeadbeef && get32(b + 236) == 0x63825363);
	CHECK(b[240] == 53 && b[242] == DHCP_DISCOVER);
	/* Our own broadcast request is not a reply. */
	struct dhcp_reply r;
	CHECK(dhcp_parse(f, len, 0xdeadbeef, &r) == 0);

	len = dhcp_build(f, mac, 7, DHCP_REQUEST, 0xc0a8012a, 0xc0a80101);
	b = f + 42;
	const uint8_t *o = b + 240;
	bool saw50 = false, saw54 = false;
	while (*o != 255) {
		if (o[0] == 50) {
			saw50 = get32(o + 2) == 0xc0a8012a;
		}
		if (o[0] == 54) {
			saw54 = get32(o + 2) == 0xc0a80101;
		}
		o += 2 + o[1];
	}
	CHECK(saw50 && saw54);
	CHECK((unsigned)(o - f) < len);

	len = make_reply(f, mac, 0x1234, DHCP_OFFER);
	CHECK(dhcp_parse(f, len, 0x1234, &r) == DHCP_OFFER);
	CHECK(r.yiaddr == 0xc0a8012a && r.server == 0xc0a80101 && r.mask == 0xffffff00 && r.router == 0xc0a80101);
	CHECK(r.lease == 86400);
	CHECK(dhcp_parse(f, len, 0x1235, &r) == 0);             /* other transaction */
	CHECK(dhcp_parse(f, 100, 0x1234, &r) == 0);             /* truncated */
	len = make_reply(f, mac, 0x1234, DHCP_ACK);
	CHECK(dhcp_parse(f, len, 0x1234, &r) == DHCP_ACK);
	/* An option running past the frame end is not read. */
	f[42 + 240 + 3] = 54;
	f[42 + 240 + 4] = 250;
	CHECK(dhcp_parse(f, len, 0x1234, &r) == DHCP_ACK && r.server == 0);
}

int
main(void)
{
	test_syscon();
	test_yt8531();
	test_lb_pick();
	test_phy();
	test_mac();
	test_csum();
	test_dhcp();
	if (failures) {
		printf("%d failures\n", failures);
		return 1;
	}
	printf("PASS\n");
	return 0;
}
