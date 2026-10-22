/*
 * Host test for the A733 framebuffer console in a733/xnu-a733-console-graphics.patch.
 * test_console_graphics_patch.py cuts the console block out of the patched
 * pexpert/arm/pe_serial.c and builds it with -include, after the stubs below.
 * The framebuffer is the real geometry: physical 1024x600, stride 4096,
 * portrait 600x1024 text rotated like Stage0.
 */
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

static uint32_t fb[600 * 1024];

static uint32_t
portrait_get(uint32_t x, uint32_t y)
{
	return fb[(600u - 1u - x) * 1024u + y];
}

/* Text of portrait row r as drawn on screen (glyph matching against iso_font). */
static void
screen_row(uint32_t r, char *out, uint32_t cols)
{
	for (uint32_t c = 0; c < cols; c++) {
		out[c] = '?';
		for (int ch = 32; ch < 127; ch++) {
			int ok = 1;
			for (uint32_t gy = 0; gy < 16 && ok; gy++) {
				for (uint32_t gx = 0; gx < 8 && ok; gx++) {
					uint32_t want = (iso_font[ch * 16 + gy] & (1u << gx)) ? FBCON_FG : FBCON_BG;
					ok = portrait_get(c * 8 + gx, r * 16 + gy) == want;
				}
			}
			if (ok) {
				out[c] = (char)ch;
				break;
			}
		}
	}
	out[cols] = 0;
	for (int i = (int)cols - 1; i >= 0 && out[i] == ' '; i--) {
		out[i] = 0;
	}
}

static void
puts_console(const char *s)
{
	while (*s) {
		fbcon_transmit_data((uint8_t)*s++);
	}
}

int
main(void)
{
	char row[80];

	/* iso_font stand-in: every printable glyph unique (row 0 = code, rows 1-15 = pattern). */
	for (int ch = 0; ch < 256; ch++) {
		for (int gy = 0; gy < 16; gy++) {
			iso_font[ch * 16 + gy] = (unsigned char)(gy == 0 ? ch : (ch * 37 + gy * 11) & 0xff);
		}
	}
	iso_font[' ' * 16] = 0;
	for (int gy = 0; gy < 16; gy++) {
		iso_font[' ' * 16 + gy] = 0;
	}

	fbcon_base = fb;
	fbcon_width = 1024;
	fbcon_height = 600;
	fbcon_stride = 4096;
	fbcon_init();
	CHECK(fbcon_rows == 64 && fbcon_cols == 75);

	/* 1. Scrolling: after 100 lines the newest is at the bottom, in order. */
	char line[32];
	for (int i = 0; i < 100; i++) {
		snprintf(line, sizeof(line), "line %03d\n", i);
		puts_console(line);
	}
	screen_row(62, row, 75);
	CHECK(strcmp(row, "line 099") == 0);
	screen_row(0, row, 75);
	CHECK(strcmp(row, "line 037") == 0);          /* 100 lines + empty cursor row: 37..99 */
	screen_row(63, row, 75);
	CHECK(row[0] == 0);                            /* cursor row, empty */
	puts_console("partial");
	screen_row(63, row, 75);
	CHECK(strcmp(row, "partial") == 0);
	puts_console("\n");

	/* Long line wraps to the next row. */
	char longl[90];
	memset(longl, 'x', 80);
	longl[80] = '\n';
	longl[81] = 0;
	puts_console(longl);
	screen_row(61, row, 75);
	CHECK(strlen(row) == 75);
	screen_row(62, row, 75);
	CHECK(strcmp(row, "xxxxx") == 0);

	/* 2. Graphics: an iOS frame is composited; console text must not damage it. */
	uint32_t y0;
	uint32_t *band = a733_fbcon_band(&y0);
	CHECK(y0 == 1024 - (8 * 16 + 8));
	for (uint32_t x = 0; x < 600; x++) {
		for (uint32_t y = 0; y < 1024; y++) {
			uint32_t color = 0xff000000u | (x * 7 + y * 13) % 0xffffffu;
			fb[(599u - x) * 1024u + y] = color;
			if (y >= y0) {
				band[(y - y0) * 600u + x] = color;
			}
		}
	}
	a733_fbcon_graphics_frame();
	a733_fbcon_overlay();
	for (int i = 0; i < 200; i++) {
		snprintf(line, sizeof(line), "daemon %03d started\n", i);
		puts_console(line);
	}
	int frame_ok = 1, band_dark_ok = 1;
	for (uint32_t x = 0; x < 600 && frame_ok; x++) {
		for (uint32_t y = 0; y < y0; y++) {
			if (portrait_get(x, y) != (0xff000000u | (x * 7 + y * 13) % 0xffffffu)) {
				frame_ok = 0;
				break;
			}
		}
	}
	CHECK(frame_ok);                               /* frame above the band untouched */
	/* Band: darkened frame (not accumulated) or white glyph pixels. */
	for (uint32_t x = 0; x < 600 && band_dark_ok; x++) {
		for (uint32_t y = y0; y < 1024; y++) {
			uint32_t orig = 0xff000000u | (x * 7 + y * 13) % 0xffffffu;
			uint32_t got = portrait_get(x, y);
			if (got != (0xff000000u | ((orig & 0xfefefeu) >> 1)) && got != 0xffffffffu) {
				band_dark_ok = 0;
				break;
			}
		}
	}
	CHECK(band_dark_ok);
	/* The newest complete log line is in the band row above the (empty) current one. */
	int white = 0;
	for (uint32_t x = 12; x < 12 + 18 * 8; x++) {
		for (uint32_t y = y0 + 6 * 16; y < y0 + 7 * 16; y++) {
			white += portrait_get(x, y) == 0xffffffffu;
		}
	}
	CHECK(white > 0);

	/* 3. A panic brings the full text console back, newest at the bottom. */
	panic_flag = 1;
	puts_console("panic: test\n");
	screen_row(62, row, 75);
	CHECK(strcmp(row, "panic: test") == 0);
	screen_row(61, row, 75);
	CHECK(strcmp(row, "daemon 199 started") == 0);

	if (failures) {
		fprintf(stderr, "%d failure(s)\n", failures);
		return 1;
	}
	printf("PASS: A733 console scrolls, keeps iOS frames intact, panic text returns\n");
	return 0;
}
