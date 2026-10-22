/*
 * Host test: the row-order CPU scaler of a733_cpu_present() (patch 9999q,
 * a733/xnu-a733-cores-fb-power.patch) must draw exactly what the previous
 * portrait-order loop drew. test_cores_fb_power_patch.py cuts the new loop
 * out of the patch into scaler_block.inc (included below); the old loop is
 * copied here verbatim. Random layers with every alpha case, the real
 * 1024x600 framebuffer and the console band are compared pixel for pixel.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SWEET_FB_LAYERS 4

struct SweetSurface {
	uint32_t width, height, bytesPerRow;
};

static const uint32_t physical_w = 1024, physical_h = 600;
static const uint32_t portrait_w = 600, portrait_h = 1024;
static const uint32_t canvas_w = 1125, canvas_h = 2436;
static const uint32_t view_w = (portrait_h * canvas_w + canvas_h / 2) / canvas_h;
static const uint32_t left = (portrait_w - view_w) / 2;

static void
old_present(SweetSurface **layers, const uint8_t **pixels, volatile uint32_t *dst, uint32_t stride,
    uint32_t *band, uint32_t band_y0)
{
	for (uint32_t y = 0; y < portrait_h; y++) {
		for (uint32_t x = 0; x < portrait_w; x++) {
			uint32_t color = 0xff000000u;
			if (x >= left && x < left + view_w) {
				uint32_t vx = x - left;
				for (uint32_t l = 0; l < SWEET_FB_LAYERS; l++) {
					const SweetSurface *s = layers[l];
					if (s == NULL) {
						continue;
					}
					uint32_t sx = (uint64_t)vx * s->width / view_w;
					uint32_t sy = (uint64_t)y * s->height / portrait_h;
					uint32_t src = 0;
					memcpy(&src, pixels[l] + (uint64_t)sy * s->bytesPerRow +
					    (uint64_t)sx * 4, sizeof(src));
					unsigned a = src >> 24;
					if (a == 255) {
						color = src;
					} else if (a != 0) {
						unsigned rb = (((src & 0xffu) * a +
						    (color & 0xffu) * (255 - a) + 127) / 255);
						unsigned g = ((((src >> 8) & 0xffu) * a +
						    ((color >> 8) & 0xffu) * (255 - a) + 127) / 255);
						unsigned r = ((((src >> 16) & 0xffu) * a +
						    ((color >> 16) & 0xffu) * (255 - a) + 127) / 255);
						color = 0xff000000u | (r << 16) | (g << 8) | rb;
					}
				}
			}
			dst[(physical_h - 1u - x) * stride + y] = color;
			if (y >= band_y0) {
				band[(y - band_y0) * portrait_w + x] = color;
			}
		}
	}
}

static void
new_present(SweetSurface **layers, const uint8_t **pixels, volatile uint32_t *dst, uint32_t stride,
    uint32_t *band, uint32_t band_y0)
{
#include "scaler_block.inc"
}

static uint32_t rng = 12345;
static uint32_t
rnd(void)
{
	rng = rng * 1103515245u + 12345u;
	return rng >> 1;
}

int
main(void)
{
	static uint32_t fb_old[1024 * 600], fb_new[1024 * 600];
	static uint32_t band_old[600 * 128], band_new[600 * 128];
	const uint32_t stride = physical_w;
	int failures = 0;

	for (int round = 0; round < 6; round++) {
		SweetSurface surf[SWEET_FB_LAYERS];
		SweetSurface *layers[SWEET_FB_LAYERS] = {};
		const uint8_t *pixels[SWEET_FB_LAYERS] = {};
		uint8_t *mem[SWEET_FB_LAYERS] = {};
		for (int l = 0; l < SWEET_FB_LAYERS; l++) {
			/* layer 0 full canvas; others sometimes absent, odd sizes, padded rows */
			if (l > 0 && (rnd() % 3) == 0) {
				continue;
			}
			uint32_t w = l == 0 ? 1125 : 40 + rnd() % 1200, h = l == 0 ? 2436 : 30 + rnd() % 2500;
			uint32_t bpr = w * 4 + (rnd() % 4) * 64;
			surf[l] = { w, h, bpr };
			mem[l] = (uint8_t *)malloc((size_t)bpr * h);
			for (size_t i = 0; i < (size_t)bpr * h; i += 4) {
				uint32_t v = rnd();
				uint32_t a = (v >> 24) % 4;    /* 0, 255, partial */
				v = (v & 0x00ffffffu) | ((a == 0 ? 0u : a == 1 ? 255u : (v >> 3) & 0xffu) << 24);
				memcpy(mem[l] + i, &v, 4);
			}
			layers[l] = &surf[l];
			pixels[l] = mem[l];
		}
		uint32_t band_y0 = round % 2 ? portrait_h - 128 : portrait_h;
		memset(fb_old, 0x55, sizeof(fb_old));
		memset(fb_new, 0xaa, sizeof(fb_new));
		memset(band_old, 0, sizeof(band_old));
		memset(band_new, 0, sizeof(band_new));
		old_present(layers, pixels, fb_old, stride, band_old, band_y0);
		new_present(layers, pixels, fb_new, stride, band_new, band_y0);
		if (memcmp(fb_old, fb_new, sizeof(fb_old)) != 0) {
			for (uint32_t i = 0; i < 1024 * 600; i++) {
				if (fb_old[i] != fb_new[i]) {
					fprintf(stderr, "round %d: pixel row %u col %u old %08x new %08x\n", round,
					    i / 1024, i % 1024, fb_old[i], fb_new[i]);
					break;
				}
			}
			failures++;
		}
		if (memcmp(band_old, band_new, sizeof(band_old)) != 0) {
			fprintf(stderr, "round %d: console band differs\n", round);
			failures++;
		}
		for (int l = 0; l < SWEET_FB_LAYERS; l++) {
			free(mem[l]);
		}
	}
	if (failures) {
		printf("FAIL (%d)\n", failures);
		return 1;
	}
	printf("A733 FB scaler: row-order loop matches the old loop: PASS\n");
	return 0;
}
