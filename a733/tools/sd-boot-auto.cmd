echo ios-a733 stage0 v3 AUTOSTART diagnostic - NOT iOS
screen_char
setenv stdout serial,vidconsole
setenv stderr serial,vidconsole
echo [1/4] U-BOOT SCRIPT RUNNING - screen_char attempted
echo Starting screen test using the inherited v59 framebuffer parameters.
echo If it hangs, power-cycle the board. Stage0 does not write storage.
sleep 2
if ext4load mmc 0:1 0x42000000 /ios-a733/stage0.uimg; then
    echo [2/4] STAGE0 FILE LOADED
    sleep 2
    if ext4load mmc 0:1 0x43000000 /dtb/allwinner/sun60i-a733-orangepi-4-pro.dtb; then
        echo [3/4] DEVICE TREE LOADED
        echo [4/4] HANDOFF TO STAGE0 VIA BOOTM / BL31 IN 2 SECONDS
        sleep 2
        bootm 0x42000000 - 0x43000000
        echo ERROR: bootm failed or stage0 returned.
    else
        echo ERROR: could not load the board Device Tree. Stage0 not started.
    fi
else
    echo ERROR: could not load stage0. Nothing started.
fi
while true; do sleep 1; done
