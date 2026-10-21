# FIRST REAL iOS FRAME — GUI-first цель Orange Pi 4 Pro

**Цель:** минимально необходимый подлинный iOS 16.7.16 (20H392) экран блокировки или SpringBoard Home Screen на HDMI Orange Pi 4 Pro. НЕ полноценный телефон и НЕ нарисованная копия. Достаточно первого CoreAnimation/IOSurface кадра; управление пальцем, сеть, аудио, модем, камера и вторые ядра — позже.

## Проверенное железом

| Этап | Статус |
| --- | --- |
| XNU 8796 на одном A76 (MPIDR 0x600), 16-KiB страницы | PASS (v19–v22) |
| HFSX RAM-root /dev/md0, оригинальный /sbin/launchd доступен | PASS (v21–v22) |
| Реальный Apple dyld начал выполняться | PASS (v22, выводит собственные ошибки) |
| libSystem.B.dylib загружен из shared cache | NO: в 16-MiB пробном RAM-root кеша нет |
| Apple launchd начал запускать службы | НЕ ПРОВЕРЕНО |
| backboardd и SpringBoard запущены | НЕ ПРОВЕРЕНО |
| CoreAnimation IOSurface present -> HDMI реальный кадр | НЕ ПРОВЕРЕНО; только регистрация AppleCLCD |
| Подлинный экран блокировки / Home Screen | НЕ ДОСТИГНУТО |

## Самый короткий путь

1. **Доступ к реальным библиотекам:** в 16-GiB корневой системе уже есть split dyld cache. Размер рабочего набора без .symbols — ~2.55 GiB. Текущий XNU payload максимум 128 MiB и A733 RAM-root максимум 16 MiB, kernel-managed память — 1 GiB. Не рассчитывать, что без проверки эти файлы можно разместить в RAM, и не удалять случайные .dylddata/.dyldlinkedit.
2. **Хранение:** главный практичный путь — сделать XNU драйвер чтения Allwinner MMC0 (A733: 0x04020000, compatible sun20i-d1-mmc) и дать ему доступ к HFS+ root на отдельной области microSD. Сначала строго read-only и bounds-checked; затем добавить безопасную запись или /private/var overlay, потому что системным службам нужен рабочий каталог данных. Не портировать Qualcomm UFS или Android modem.
3. **Запуск Apple launchd:** оставить `unentitled_ios_sim_launch=1`, `ignition_level=1` и условия доступа к полному dyld cache. Исправлять конкретные kernel/XPC errors из журналов.
4. **GUI:** добиваться `backboardd` -> SpringBoard, живого `IOCoreSurfaceRoot` / `AppleCLCD` и одного успешного вызова A733 `present()` с ненулевыми IOSurface пикселями.
5. **Первый скрин:** убрать диагностический оверлей через `a733fb_logs=0` только после доказанного первого кадра; не маскировать ошибки раньше.

**Один A76 оставляем всегда.** Пользователь должен сохранить v22 для отката. Нельзя заявлять успех по строке AppleCLCD READY — это только регистрация сервиса.

## Минимально важные компоненты userland

Сохраняем оригинальные `/sbin/launchd`, `/usr/lib/dyld`, цельный набор arm64 `dyld_shared_cache`, `/System/Library/xpc/launchd.plist`, `xpcproxy`, `runningboardd`, `backboardd`, `SpringBoard` и службы, которые действительно потребуют их зависимости. Список **не гарантирует** замкнутость зависимостей: реальные ошибки выясняем журналами, а не отключением большинства из 532 launchd jobs наугад.

Ни Wi-Fi, ни GPU-ускорение, ни работающий сенсор не являются обязательными для первого кадра, но графический ABI (IOSurface, CoreAnimation, IOMobileFramebuffer) и нужные XPC сервисы обязательны.

## Подготовка реального RootFS к GUI, не меняя эталон

Наш 16-GiB серверный файл: `/root/ios-root-work/ios16-root.img`. Не менять его: он нужен как исходный HFS+ образ. Ветка `opi4pro` содержит оригинальный upstream `tools/sweet-root-tweaks.py` и наш `a733/tools/prepare_gui_root_clone.sh`. Скрипт создаёт новую копию, **только к ней** применяет авторские изменения, затем проверяет файловую систему.

На Linux-сервере с root-доступом, по мере готовности к XNU SD-тестам:

```bash
cd /root/ios-root-work
git -C a733-repo pull --ff-only
sudo bash a733-repo/a733/tools/prepare_gui_root_clone.sh \
  /root/ios-root-work/ios16-root.img \
  /root/ios-root-work/ios16-gui-first.img
```

Требует свободного места для отдельной 16-GiB копии, работоспособных loop/hfsplus и `fsck.hfsplus`. Если команда завершится ошибкой, **не используйте** получившийся образ без проверки. Исходный `ios16-root.img` останется неизменным.

`ios16-gui-first.img` — это HFS+ том, а **не** bootable SD IMG. Скрипт НЕ устанавливает XNU SD-драйвер, НЕ доказывает работоспособность Apple launchd и НЕ создаёт RAM-диск. Не записывать его поверх всей microSD; позднее нужен отдельный раздел с корректной таблицей разделов и сохранением U-Boot.

## У автора уже установлено

В `MakrSas/ios-topaz` реальный SpringBoard появился после исправлений подлинного IOSurface/IOMFB, IOKit, AppleKeyStore, рабочей HFS root, sandbox/entitlements, работы XPC и Setup/activation. Для нас полезны именно эти уровни; Qualcomm UFS/MDP, touch и modem напрямую на A733 переносить нельзя.

A733 MMC0: 0x04020000, IRQ 161, совместим с D1; исследователь Linux описал работающие PIO SD-чтения и сбой IDMAC. Для первого безопасного XNU чтения разумен **PIO**, но это пока план — на реальной A733 плате под XNU не подтверждён.

## Текущая задача

**Первый GUI кадр, не новый функционал телефона.** Следующий коммит с XNU read-only MMC0 probe должен отдельно доказывать, что чтение блока с microSD безопасно и совпадает с U-Boot/Linux, прежде чем показывать полный root XNU. Не перепрошивать рабочую v22 на основании непроверенного кода.
