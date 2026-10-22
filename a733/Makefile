CROSS ?= aarch64-linux-gnu-
CC := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
HOSTCC ?= cc

CFLAGS := -O2 -std=c11 -Wall -Wextra -ffreestanding -fno-builtin \
          -fno-stack-protector -fno-pic -fno-pie -mcpu=cortex-a55 \
          -mstrict-align -mgeneral-regs-only -I src
LDFLAGS := -nostdlib -nostartfiles -no-pie -Wl,--build-id=none \
           -Wl,-Map=build/stage0.map -T linker.ld

.PHONY: all test test-boot test-hardware-fdt test-real-xnu check-a733-xnu preview clean
all: build/stage0.uimg

build:
	mkdir -p build

build/start.o: src/start.S Makefile | build
	$(CC) $(CFLAGS) -c $< -o $@

build/boot.o: src/boot.c src/display.h src/cache.h Makefile | build
	$(CC) $(CFLAGS) -c $< -o $@

build/display.o: src/display.c src/display.h src/font.h Makefile | build
	$(CC) $(CFLAGS) -c $< -o $@

build/cache.o: src/cache.c src/cache.h Makefile | build
	$(CC) $(CFLAGS) -c $< -o $@

build/fdt_safe.o: src/fdt_safe.c src/fdt_safe.h Makefile | build
	$(CC) $(CFLAGS) -c $< -o $@

build/xnu_payload.o: src/xnu_payload.c src/xnu_payload.h src/display.h Makefile | build
	$(CC) $(CFLAGS) -c $< -o $@

build/xnu_boot.o: src/xnu_boot.c src/xnu_boot.h src/xnu_payload.h src/fdt_safe.h Makefile | build
	$(CC) $(CFLAGS) -c $< -o $@

build/gic_a733.o: src/gic_a733.c src/gic_a733.h Makefile | build
	$(CC) $(CFLAGS) -c $< -o $@

build/stage0.elf: build/start.o build/boot.o build/display.o build/cache.o build/fdt_safe.o build/xnu_payload.o build/xnu_boot.o build/gic_a733.o linker.ld
	$(CC) $(LDFLAGS) build/start.o build/boot.o build/display.o build/cache.o build/fdt_safe.o build/xnu_payload.o build/xnu_boot.o build/gic_a733.o -o $@

build/stage0.bin: build/stage0.elf
	$(OBJCOPY) -O binary $< $@

build/stage0.uimg: build/stage0.bin tools/make_uimage.py
	python3 tools/make_uimage.py $< $@

build/test_display: src/display.c src/display.h src/font.h tests/test_display.c | build
	$(HOSTCC) -std=c11 -O2 -Wall -Wextra -Werror -I src \
		src/display.c tests/test_display.c -o $@

test: build/test_display
	./build/test_display
	python3 tests/test_adt.py
	python3 tests/test_uimage_format.py
	python3 tests/test_boot_script.py
	$(HOSTCC) -std=c11 -O2 -Wall -Wextra -Werror -DA733_HOST_TEST -I src \
		src/xnu_payload.c tests/test_xnu_payload.c -o build/test_xnu_payload
	./build/test_xnu_payload
	$(HOSTCC) -std=c11 -O2 -Wall -Wextra -Werror -I src \
		src/fdt_safe.c tests/test_fdt_safe.c -o build/test_fdt_safe
	./build/test_fdt_safe
	python3 tests/test_xnu_script.py
	python3 tests/test_adapt_xnu.py
	python3 tests/test_a76_probe_script.py
	python3 -m unittest discover -s tests -p test_sdmmc_patch.py -v
	python3 -m unittest discover -s tests -p test_sdlog_tool.py -v
	python3 -m unittest discover -s tests -p test_sdcard_layout.py -v
	python3 -m unittest discover -s tests -p test_console_graphics_patch.py -v
	python3 -m unittest discover -s tests -p test_smp_a76_patch.py -v
	python3 -m unittest discover -s tests -p test_bootpart.py -v
	python3 -m unittest discover -s tests -p test_usbtouch_patch.py -v
	python3 -m unittest discover -s tests -p test_cores_fb_power_patch.py -v

test-boot: all
	python3 tests/test_boot_image.py

build/test_fdt_region: src/fdt_safe.c src/fdt_safe.h tests/test_fdt_region.c | build
	$(HOSTCC) -std=c11 -O2 -Wall -Wextra -Werror -I src \
		src/fdt_safe.c tests/test_fdt_region.c -o $@

# Requires the untouched vendor ZIP captured from the physical Orange Pi.
test-hardware-fdt: build/test_fdt_region
	unzip -p ../upload/OrangePi4Pro-EDK2-v59-and-DeviceTree-20261019.zip \
		DeviceTree/sun60i-a733-orangepi-4-pro.dtb | ./build/test_fdt_region static
	unzip -p ../upload/OrangePi4Pro-EDK2-v59-and-DeviceTree-20261019.zip \
		DeviceTree/live-expanded-fdt.dtb | ./build/test_fdt_region live

# Optional, requires a REAL, already-built XNU Mach-O. The upstream kernel
# is still Qualcomm-specific until the A733 source adaptations are rebuilt.
TOPAZ_ROOT ?= ..
XNU_MACHO ?= build/kernel.development.sweet
build/a733-xnu.payload: build/a733-early.adt $(XNU_MACHO)
	python3 tools/package_xnu_a733.py $(XNU_MACHO) build/a733-early.adt $@ \
		--cmdline 'debug=0xc keepsyms=1 cpus=1 -v modem=0 wifi=0'

build/test_real_xnu_payload: src/xnu_payload.c src/xnu_payload.h tests/test_real_xnu_payload.c | build
	$(HOSTCC) -std=c11 -O2 -Wall -Wextra -Werror -DA733_HOST_TEST -I src \
		src/xnu_payload.c tests/test_real_xnu_payload.c -o $@

test-real-xnu: build/test_real_xnu_payload build/a733-xnu.payload
	./build/test_real_xnu_payload build/a733-xnu.payload

# Mandatory before a FIRST REAL XNU flash image. Deliberately FAILS against
# the successful but UNADAPTED topaz CI kernel; packaging alone is not enough.
check-a733-xnu:
	python3 tools/audit_a733_macho.py $(XNU_MACHO)

build/a733-early.adt: tools/mkadt_a733.py | build
	python3 $< $@

adt: build/a733-early.adt

build/host_preview: src/display.c src/display.h src/font.h tools/host_preview.c | build
	$(HOSTCC) -std=c11 -O2 -Wall -Wextra -Werror -I src \
		src/display.c tools/host_preview.c -o $@

preview: build/host_preview
	./build/host_preview build/portrait-preview.ppm
	convert build/portrait-preview.ppm build/portrait-preview.png

clean:
	rm -f build/start.o build/boot.o build/display.o build/cache.o build/stage0.elf \
	      build/stage0.bin build/stage0.uimg build/stage0.map build/test_display \
	      build/host_preview build/portrait-preview.ppm build/portrait-preview.png
