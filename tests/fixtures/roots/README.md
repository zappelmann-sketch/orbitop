# Test trees

Fake `/proc` and `/sys` roots. Every reader takes a `root` argument; tests pass one of these.
`setup-privileges.sh` reads them via `ORBITOP_SYSROOT`.

| Tree | Content |
|---|---|
| `intel-laptop` | Captured with `scripts/capture-fixture.sh` on the reference machine (i7-7600U, i915, RAPL, battery). `energy_uj` is only present if it was readable at capture time (it is root-only by default; re-capture after running `setup-privileges.sh`). |
| `amd-desktop` | Hand-built: 16 threads; `k10temp` (`temp1_label=Tctl`); `nct6775` with `fan1..3`, `temp1..3`; `card0` driver `amdgpu` (`gpu_busy_percent=37`, VRAM 3 of 8 GiB, `pp_dpm_sclk` line `1: 1850Mhz *`, hwmon5 with `power1_average=45000000`, `temp1_input=61000`); `card1` driver `nvidia`, vendor `0x10de`; `intel-rapl:0` `package-0`; `nvme0n1`, `sda` with `drivetemp` hwmon; `enp5s0`, `docker0`, `veth1a2b`; no battery. |
| `arm-board` | Hand-built: `/proc/cpuinfo` without `model name`, with `Model : Raspberry Pi 5 Model B`; 4 threads; `thermal_zone0` (`cpu-thermal`, 52000), `thermal_zone1` (`gpu-thermal`, 48000); `card0` driver `v3d` with `devfreq` `cur_freq=500000000`, `max_freq=960000000`; `mmcblk0` with `mmcblk0p1`, `mmcblk0p2`; `eth0`, `wlan0`; no hwmon fan, no RAPL, no battery. |
| `vm` | Hand-built: 2 threads, `vda`, `ens3`, `lo`; no hwmon, thermal, drm, powercap or power_supply. |

Conventions:

- The amdgpu hwmon exists twice, as `sys/class/hwmon/hwmon5` and, through a relative symlink, as `sys/class/drm/card0/device/hwmon/hwmon5` (as on real systems).
- `device/driver` is a (dangling) symlink to `../../../bus/pci/drivers/<name>`.
- A NIC is physical when `sys/class/net/<if>/device` exists (empty directory); `lo`, `docker0` and `veth*` have none.
- Partitions appear as subdirectories of their disk under `sys/block/<disk>/`.

## Re-capturing `intel-laptop`

```sh
sudo bash scripts/setup-privileges.sh      # makes energy_uj readable
bash scripts/capture-fixture.sh tests/fixtures/roots/intel-laptop
```

The script copies only the file globs it lists, skips unreadable files, and never copies serials,
MAC addresses, hostnames or mounts under home/media/snap. After capturing, grep the tree for the
hostname, the user name and MAC addresses before committing.
