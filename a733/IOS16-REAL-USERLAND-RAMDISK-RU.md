# Реальный iOS 16 на A733: этап RAM-root preflight

**Статус: предварительная проверка готова; реальный Apple launchd ещё не запускался на Orange Pi.**

Наша цель — оригинальный iOS 16.7.16 (iPhone X, сборка 20H392), НЕ копия интерфейса. v20 аппаратно подтверждает регистрацию AppleCLCD и запуск тестового PID 1, но RAM-root содержит только наш собственный Mach-O.

## Источник

Официальная IPSW для iPhone10,3/D22AP: https://ipsw.me/download/iPhone10%2C3/20H392/ (переход на сервер Apple). Название: iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw; ~5.7 GiB; SHA-256: ece1194f7e233e9109c5790a8d23a4564a10a254e15ec5b09978a343265568fb.

IPSW — источник оригинальных Apple файлов, это НЕ прошивка для Orange Pi. В нашем форке присутствуют оригинальные upstream tools/mkiosroot.sh и tools/sweet-root-tweaks.py. Сборку полного root из OS.dmg, SystemOS.dmg и AppOS.dmg см. https://github.com/MakrSas/ios-topaz#2-build-the-ios-root-image.

После извлечения трёх DMG (для D22AP Erase identity), на ПК с Linux, apfs-fuse, hfsprogs и rsync:

    sudo bash tools/mkiosroot.sh OS.dmg SystemOS.dmg AppOS.dmg ios16-root.img 16G
    sudo mkdir -p /mnt/iosroot
    sudo mount -t hfsplus -o loop,ro ios16-root.img /mnt/iosroot
    python3 a733/tools/inspect_ios16_root.py /mnt/iosroot --json a733-ios16-preflight.json
    sudo umount /mnt/iosroot

16 GiB — размер тома у автора ios-topaz, НЕ подтверждённый минимальный объём системы.

## Что проверяем

- Настоящие ARM64 Mach-O /sbin/launchd и /usr/lib/dyld (динамический загрузчик, load commands).
- System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64 и нумерованные companion-файлы из SystemOS Cryptex.
- System/Library/xpc/launchd.plist, словарь LaunchDaemons.
- Версию ОС через SystemVersion.plist.
- Фактический объём и соответствие нынешним ограничениям Stage0 и RAM-root.

Скрипт не изменяет Apple бинарники, ничего не прошивает, не обходит активацию. При ошибках или отсутствии файлов сообщает о них. --stage создаёт лишь диагностическую копию нескольких файлов; она НЕ является полной загрузочной системой.

## Технические ограничения v20

- A733 package_xnu_a733.py: размер RAM-root не более 16 MiB.
- Stage0 xnu_payload.h: A733XNU1 payload не более 128 MiB.
- Аппаратно проверенный AutoBoot IMG имеет размер 64 MiB.
- В iOS/XNU выделен 1 GiB верхней RAM (0x100000000…0x140000000).
- Собранный CI v20 payload с 8-MiB тестовой root занимает 25 471 696 байт.

После измерения реальных Apple файлов нужно либо безопасно расширять загрузчик/размещение RAM-root с проверками, либо использовать постоянный накопитель. У 4-ГБ платы может не хватить памяти для большого RAM-диска и одновременной работы SpringBoard; обещать результат заранее нельзя.

## Дальше

1. Получаем подлинные Apple OS/SystemOS/AppOS DMG и запускаем preflight.
2. Считаем минимальный реально необходимый объём и зависимости. Не обещаем, что весь SpringBoard поместится в RAM.
3. Только после подтверждения размеров готовим новый экспериментальный HFS+ RAM-root и Stage0 с отдельной загрузочной проверкой. Рабочую v20 сохраняем.
4. Проверяем настоящий dyld и launchd, при сбоях собираем логи Mach IPC, процессов, служб, IOKit.
5. После запуска backboardd/CoreAnimation проверяем реальные IOSurface кадры и оригинальный SpringBoard.

**Без IPSW или извлечённых реальных системных файлов нельзя честно создать образ с настоящей iOS.** В GitHub не загружаем закрытые Apple binaries. Второе ядро не включаем.
