# Реальный iOS 16 на A733: этап RAM-root preflight

**Статус: предварительная проверка готова; реальный Apple launchd ещё не запускался на Orange Pi.**

Наша цель — оригинальный iOS 16.7.16 (iPhone X, сборка 20H392), НЕ копия интерфейса. v20 аппаратно подтверждает регистрацию AppleCLCD и запуск тестового PID 1, но RAM-root содержит только наш собственный Mach-O.

## Источник

Официальная IPSW для iPhone10,3/D22AP: https://ipsw.me/download/iPhone10%2C3/20H392/ (переход на сервер Apple). Название: iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw; ~5.7 GiB; SHA-256: ece1194f7e233e9109c5790a8d23a4564a10a254e15ec5b09978a343265568fb.

IPSW — источник оригинальных Apple файлов, это НЕ прошивка для Orange Pi. В нашем форке присутствуют оригинальные upstream tools/mkiosroot.sh и tools/sweet-root-tweaks.py. Сборку полного root из OS.dmg, SystemOS.dmg и AppOS.dmg см. https://github.com/MakrSas/ios-topaz#2-build-the-ios-root-image.

Новый автономный скрипт ищет ровно три DMG по **Apple BuildManifest.plist / D22AP / Erase identity** и не угадывает имена файлов (работает в Windows, macOS или Linux с обычным Python 3):

    python3 a733/tools/extract_iphone_x_ipsw.py iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw --json ipsw-components.json
    python3 a733/tools/extract_iphone_x_ipsw.py iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw --extract extracted

Первая команда только анализирует архив. Вторая извлекает оригинальные extracted/OS.dmg, extracted/SystemOS.dmg и extracted/AppOS.dmg в **новую** папку; потребуется место на диске. Пользователь может отправить нам только небольшие JSON-отчёты — не нужно загружать в GitHub оригинальные Apple DMG.

После извлечения трёх DMG (для D22AP Erase identity), на ПК с Linux, apfs-fuse, hfsprogs и rsync:

    sudo bash tools/mkiosroot.sh extracted/OS.dmg extracted/SystemOS.dmg extracted/AppOS.dmg ios16-root.img 16G
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

## Реальный собранный Apple root — отчёт 21 октября 2026

Пользователь собрал на собственном Linux-сервере подлинный iOS 16.7.16 (20H392) из iPhone X IPSW через готовые инструменты ios-topaz. Отчёт с побайтовой сверкой 7 Apple компонентов получен, но сами проприетарные файлы остаются на сервере, НЕ в публичном GitHub.

- HFS+ образ: **16 GiB**; FS check read-only PASS; занято **11.67 GiB**.
- Apple /sbin/launchd: **541600 байт**; /usr/lib/dyld: **922912 байт**; корректные thin ARM64 Mach-O. Оригинальность этих и других пяти системных файлов подтверждена в отчёте по SHA-256.
- Полная split `dyld_shared_cache_arm64`: **3,330,359,296 байт**; без `.symbols` — **2,738,257,920 байт (2.55 GiB)**, включая `.NN.dylddata` и `.NN.dyldlinkedit`. Нельзя удалить эти части наугад и считать cache рабочим.
- Более 500 launchd jobs. /usr/lib/libSystem.B.dylib отсутствует отдельным файлом: его код обычно находится в dyld shared cache (это не самостоятельная ошибка сборки).
- Есть 2 ошибки пути в тайских образцах Shortcuts (названия, нормализация Unicode). Отчёт `inventory.complete=false` — это не свидетельство 100% побайтовой проверки всех 181765 файлов.
- Никакого реального запуска Apple launchd/dyld на A733 этот отчёт пока не доказывает.

### Первый диагностический Apple Mach-O эксперимент (без shared cache)

**Следующая тестовая задача — не SpringBoard**, а проверить первую реальную попытку XNU запустить подписанный Apple `/sbin/launchd` и начать выполнять `/usr/lib/dyld`. Создан скрипт [make_apple_launchd_probe_ramdisk.sh](tools/make_apple_launchd_probe_ramdisk.sh), который формирует отдельный 16-MiB HFSX том **без кеша**. Такой первый тест почти наверняка завершится ошибкой dyld, но покажет конкретную границу работоспособности exec/Mach-O; не следует ошибочно объявлять ядро/ядро+dyld «запущенной iOS».

На сервере (под root, репозиторий свежий):

```bash
cd /root/ios-root-work
git clone --depth 1 --branch orangepi-4-pro https://github.com/Kiril-Donec/ios-opi4pro.git a733-repo
mkdir -p iosroot-mnt
mount -t hfsplus -o loop,ro,force ios16-root.img iosroot-mnt
bash a733-repo/a733/tools/make_apple_launchd_probe_ramdisk.sh iosroot-mnt a733-apple-launchd-probe.hfs
umount iosroot-mnt
sha256sum a733-apple-launchd-probe.hfs
```

Если репозиторий уже существует, обновить его `git -C a733-repo pull --ff-only` вместо повторного `git clone`. Файл `a733-apple-launchd-probe.hfs` будет иметь **16 MiB** и содержать оригинальные файлы Apple (не публиковать в GitHub). Не записывай этот HFSX напрямую на microSD: это **RAM-root data only**, НЕ 64-MiB AutoBoot IMG. После подготовки передать его отдельно для локальной упаковки следующего экспериментального IMG (вне публичного GitHub).

Следующий будущий этап — boot-time диагностика ошибки/успеха dyld и решение, как сделать полноценные зависимости доступными (SD/MMC или иной способ), сохраняя физически подтверждённый v20 и одно ядро Cortex-A76.

---

## Результат физического теста v21: Apple launchd, EXEC WRONG_PLATFORM (2026-10-21)

Пользователь физически загрузил экспериментальный v21 с **оригинальным** iPhone X /sbin/launchd на Orange Pi 4 Pro. По фотографиям HDMI:
- Один Cortex-A76 MPIDR 0x600; XNU/IOKit/BSD и AppleCLCD зарегистрированы;
- HFS+ том A733APPLE смонтирован как md0;
- XNU попытался загрузить /usr/appleinternal/sbin/launchd.development (ENOENT), затем /sbin/launchd;
- после копирования пути, namei lookup, загрузка остановилась kernel panic: `unexpected SIGKILL of launchd (CS_KILLED) reason -- namespace 9 code 0xe`.

В XNU `OS_REASON_EXEC=9`, `EXEC_EXIT_REASON_WRONG_PLATFORM=14 (0xe)`, так что это **отказ проверки платформы exec**, а не уже доказанный крах Apple dyld. `CS_KILLED` — процессный флаг, сам по себе он не раскрывает причину. В исходниках XNU для macOS-hosted iOS binaries проверка в `check_for_signature` может выдавать этот код при отсутствии `psa_platform=PLATFORM_IOS` и непредоставленном исключении. Upstream ios-sweet и ios-topaz используют boot arg `unentitled_ios_sim_launch=1`; мы его в v21 пропустили.

**Следующий диагностический эксперимент: v22**, который берёт физически проверенную v21 и изменяет ТОЛЬКО 608-байтный cmdline A733XNU1, добавляя `unentitled_ios_sim_launch=1`. Все байты SD IMG вне этого поля, kernel, HFSX RAM-root, один A76 и U-Boot неизменны (проверено побайтово при локальной упаковке). Контрольный SHA256 v22 IMG: `d8cf80fb6bdc09e6d19cccaf652153bc0f127ec556273f04239bb6d2026c2fd9`.

Ожидаемый исход: либо kernel пропустит платформенную проверку и мы увидим следующую ошибку (скорее всего, отсутствует dyld shared cache), либо потребуется исследовать другой путь `WRONG_PLATFORM` в фактически скомпилированном XNU. **Это НЕ доказательство, что Apple launchd начал работать; v22 пока не прошёл физический тест.** v20 остаётся неизменным откатом.

## Физический результат v22 — настоящий Apple dyld достиг загрузки зависимостей

По четырём HDMI-фотографиям пользователя от 2026-10-21 экспериментальный v22 с `unentitled_ios_sim_launch=1` **устранил предыдущую ошибку `EXEC_EXIT_REASON_WRONG_PLATFORM`**.

Подтверждено:
- XNU стартовал на **единственном A76 MPIDR 0x600**, `1/1 CPUs initialized`; AppleCLCD/IOSurface зарегистрированы;
- подлинные HFSX `/sbin/launchd` и `/usr/lib/dyld` доступны на RAM-root;
- **оригинальный Apple `dyld` действительно исполнил код** и самостоятельно вывел в HDMI-консоль диагностику зависимости.

Последняя полезная ошибка (фото, конец экрана):
```
Library not loaded: /usr/lib/libSystem.B.dylib
Referenced from: /sbin/launchd
Reason: tried:
  /usr/lib/libSystem.B.dylib (no such file, no dyld cache)
  /usr/local/lib/libSystem.B.dylib (no such file)
Failed to generate core file for pid: 1
panic: initproc failed to start -- exit reason namespace 6 subcode 0x1
```

`namespace 6` = `OS_REASON_DYLD`; `subcode 1` = dyld library missing. Это **предсказуемый результат** 16-MiB *diagnostic-only* RAM-диска без настоящего dyld shared cache, НЕ доказательство ошибки в самом Apple `launchd`. `launchd` пока не прошёл динамическую линковку, не запустил ни одного daemon и не вывел iOS GUI.

**Решение для следующего этапа:** не продолжать менять bootargs наугад. На сервере есть полный, валидированный 16-GiB образ. В нём `libSystem.B.dylib` находится внутри разделённого Apple shared cache (вся обязательная часть ~2.55 GiB). Возможны:
1. Эксперимент с извлечением **отдельных библиотек** через `ipsw dyld extract`, с учётом *транзитивных зависимостей*. Важно: команда документации ipsw ориентирована на анализ и **не гарантирует**, что извлечённые dylib можно напрямую исполнять на XNU без shared cache (могут остаться относительные ссылки/фиксации/подпись).
2. Реализовать XNU-доступ к внешнему накопителю microSD (read-only сначала) и использовать полный dyld shared cache без 2.55-GiB копии в RAM.
3. Экспериментальный увеличенный RAM-root, если измеренный минимальный рабочий набор действительно вмещается в память. Существующие лимиты Stage0 (payload 128 MiB, kernel-managed 1 GiB) нельзя снять простым изменением констант без проверки физической карты памяти, U-Boot областей и использования VM.

Рабочие изображения v20/v21/v22 сохранить как rollback. **Ни один новый IMG v23 этим результатом пока не обоснован.**

## Дальше

1. ~~Получаем подлинные Apple OS/SystemOS/AppOS DMG и собираем полный root.~~ DONE на сервере; семь ключевых Apple файлов и FS проверены.
2. **Измерено:** полный cache 2.55 GiB без symbols, полная root заняла 11.67 GiB. Считаем минимальный реально необходимый объём и зависимости. Не обещаем, что весь SpringBoard поместится в RAM.
3. Только после подтверждения размеров готовим новый экспериментальный HFS+ RAM-root и Stage0 с отдельной загрузочной проверкой. Рабочую v20 сохраняем.
4. ~~Первый запуск оригинального dyld~~ DONE на плате v22 (ошибка отсутствующей libSystem). Для реального запуска Apple launchd нужны доступные библиотеки и следующие логи.
5. После запуска backboardd/CoreAnimation проверяем реальные IOSurface кадры и оригинальный SpringBoard.

**Без IPSW или извлечённых реальных системных файлов нельзя честно создать образ с настоящей iOS.** В GitHub не загружаем закрытые Apple binaries. Второе ядро не включаем.
