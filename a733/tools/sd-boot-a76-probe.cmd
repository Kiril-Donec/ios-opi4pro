# Read-only A76 PSCI diagnostic; no XNU payload necessary.
# Invoke manually from v59 U-Boot only after cross-building stage0 v4.
echo ios-a733 v4 A76 PSCI probe - no storage writes
screen_char
setenv stdout serial,vidconsole
setenv stderr serial,vidconsole
if ext4load mmc 0:1 0x42000000 /ios-a733/stage0-v4.uimg; then
    if ext4load mmc 0:1 0x43000000 /dtb/allwinner/sun60i-a733-orangepi-4-pro.dtb; then
        if fdt addr 0x43000000; then
            if fdt resize 0x2000; then
                if fdt set /chosen a733,a76-probe <0x1>; then
                    echo Calling PSCI CPU_ON from stage0. Watch HDMI.
                    bootm 0x42000000 - 0x43000000
                    echo ERROR: bootm returned.
                fi
            fi
        fi
    fi
fi
echo A76 PROBE STOPPED - no storage modified
while true; do sleep 1; done
