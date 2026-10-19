# EXPERIMENTAL. This is NOT the working v3 autostart boot.cmd.
# Run only on a disposable card after compiling a genuine A733 XNU kernel.
echo ios-a733 v4 EXPERIMENTAL XNU handoff - NO STORAGE WRITES
screen_char
setenv stdout serial,vidconsole
setenv stderr serial,vidconsole
if ext4load mmc 0:1 0x42000000 /ios-a733/stage0-v4.uimg; then
    echo V4 SHIM LOADED
    if ext4load mmc 0:1 0x43000000 /dtb/allwinner/sun60i-a733-orangepi-4-pro.dtb; then
        echo FDT LOADED
        if ext4load mmc 0:1 0x52000000 /ios-a733/xnu.payload; then
            echo XNU PAYLOAD LOADED
            if setexpr a733_end 0x52000000 + ${filesize}; then
                if fdt addr 0x43000000; then
                    if fdt resize 0x2000; then
                        if fdt set /chosen a733,xnu-payload-start <0x0 0x52000000>; then
                            if fdt set /chosen a733,xnu-payload-end <0x0 ${a733_end}>; then
                                echo BOOTM HANDOFF - A76 MPIDR 0x600
                                bootm 0x42000000 - 0x43000000
                                echo ERROR: bootm returned.
                            fi
                        fi
                    fi
                fi
            fi
        fi
    fi
fi
echo EXPERIMENTAL BOOT STOPPED - no storage modified.
while true; do sleep 1; done
