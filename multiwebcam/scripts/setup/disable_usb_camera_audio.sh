#!/usr/bin/env bash
set -euo pipefail

USB_DEVICE="${1:-2-1.4}"
RULE_PATH="/etc/udev/rules.d/99-multiwebcam-disable-usb-camera-audio.rules"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0 [current-usb-device-path] [--install-udev]" >&2
  exit 1
fi

unbind_audio_interfaces() {
  local device="$1"
  local found=0

  if ! device_has_video_interface "${device}"; then
    echo "${device} has no USB video interface; leaving USB audio alone"
    return
  fi

  for interface_path in /sys/bus/usb/devices/"${device}":*; do
    [[ -d "${interface_path}" ]] || continue
    [[ -f "${interface_path}/bInterfaceClass" ]] || continue
    [[ "$(cat "${interface_path}/bInterfaceClass")" == "01" ]] || continue

    local interface_name
    interface_name="$(basename "${interface_path}")"
    found=1

    if [[ -e "/sys/bus/usb/drivers/snd-usb-audio/${interface_name}" ]]; then
      printf '%s' "${interface_name}" > /sys/bus/usb/drivers/snd-usb-audio/unbind
      echo "Unbound snd-usb-audio from ${interface_name}"
    else
      echo "Audio interface ${interface_name} is not currently bound to snd-usb-audio"
    fi
  done

  if [[ "${found}" -eq 0 ]]; then
    echo "No USB audio interfaces found for ${device}" >&2
  fi
}

device_has_video_interface() {
  local device="$1"
  for interface_path in /sys/bus/usb/devices/"${device}":*; do
    [[ -d "${interface_path}" ]] || continue
    [[ -f "${interface_path}/bInterfaceClass" ]] || continue
    [[ "$(cat "${interface_path}/bInterfaceClass")" == "0e" ]] && return 0
  done
  return 1
}

install_udev_rule() {
  cat > "${RULE_PATH}" <<EOF
# multiwebcam: keep USB camera video interfaces, but disable USB audio
# interfaces on composite USB video devices. This stops repeated
# snd-usb-audio kernel errors from webcam microphones without disabling
# standalone USB microphones or sound cards.
ACTION=="add", SUBSYSTEM=="usb", DEVTYPE=="usb_interface", ATTR{bInterfaceClass}=="01", RUN+="/bin/sh -c 'k=%k; dev=\${k%%:*}; has_video=0; for f in /sys/bus/usb/devices/\${dev}:*/bInterfaceClass; do test -r \"\$f\" || continue; test \"\$(cat \"\$f\")\" = \"0e\" && has_video=1 && break; done; test \"\$has_video\" = 1 && test -e /sys/bus/usb/drivers/snd-usb-audio/%k && echo -n %k > /sys/bus/usb/drivers/snd-usb-audio/unbind'"
EOF
  udevadm control --reload-rules
  udevadm trigger --subsystem-match=usb --action=add
  echo "Installed ${RULE_PATH} for USB audio interfaces on composite USB video devices"
}

unbind_audio_interfaces "${USB_DEVICE}"

if [[ "${2:-}" == "--install-udev" ]]; then
  install_udev_rule "${USB_DEVICE}"
fi
