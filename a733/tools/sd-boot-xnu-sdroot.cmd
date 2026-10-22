echo A733 XNU SDROOT - iOS root on microSD partition 2 - SINGLE A76 - EXPERIMENTAL
screen_char
setenv stdout serial,vidconsole
setenv stderr serial,vidconsole
if ext4load mmc 0:1 0x42000000 /ios-a733/stage0.uimg; then
    echo A733 SDROOT: stage0 loaded
    if ext4load mmc 0:1 0x43000000 /dtb/allwinner/sun60i-a733-orangepi-4-pro.dtb; then
        echo A733 SDROOT: FDT loaded
        if ext4load mmc 0:1 0x52000000 /ios-a733/a733-xnu.payload; then
            echo A733 SDROOT: XNU payload loaded
            if setexpr a733_end 0x52000000 + 0x${filesize}; then
                if fdt addr 0x43000000; then
                    if fdt resize 0x2000; then
                        if fdt set /chosen a733,xnu-payload-start <0x0 0x52000000>; then
                            if fdt set /chosen a733,xnu-payload-end <0x0 0x${a733_end}>; then
                                echo A733 SDROOT: bootm handoff to Cortex-A76
                                bootm 0x42000000 - 0x43000000
                                echo ERROR: bootm returned
                            fi
                        fi
                    fi
                fi
            fi
        fi
    fi
fi
echo ERROR: A733 SDROOT bootstrap failed; previous UEFI script kept as /boot-uefi-v59.scr
while true; do sleep 1; done
