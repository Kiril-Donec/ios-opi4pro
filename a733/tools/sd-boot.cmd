echo ios-a733 stage0 diagnostic SD card
setenv stdout serial,vidconsole
setenv stderr serial,vidconsole
echo This is NOT iOS or an XNU kernel.
echo Stage0 is NOT started automatically: framebuffer 0xBBF11000 is unverified.
echo Verify the actual framebuffer address, geometry and reservation first.
echo Files are in /ios-a733 on the ext4 partition.
echo Press Ctrl+C for the U-Boot prompt. No storage writes are performed here.
while true; do sleep 1; done
