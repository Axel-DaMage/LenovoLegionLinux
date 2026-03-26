# LenovoLegionLinux

> **[ES] VERSIÓN FINAL**
> Fork personal adaptado exclusivamente para el **Lenovo Legion 5 15ARH05 (82B5)** en Arch Linux.
> La versión **v0.0.27** es la versión final. No se realizarán más cambios.
> Para otros modelos usa el proyecto original: [johnfanv2/LenovoLegionLinux](https://github.com/johnfanv2/LenovoLegionLinux)

> **[EN] FINAL RELEASE**
> Personal fork adapted exclusively for the **Lenovo Legion 5 15ARH05 (82B5)** on Arch Linux.
> Version **v0.0.27** is the final release. No further changes will be made.
> For other models use the original project: [johnfanv2/LenovoLegionLinux](https://github.com/johnfanv2/LenovoLegionLinux)

---

Fan curve control, power modes, and hardware monitoring for the Lenovo Legion 5 15ARH05 (82B5).

## Install (Arch Linux)

**Step 1 — dependencies:**

```bash
sudo pacman -S --needed linux-headers base-devel dkms python-pyqt6 python-yaml python-argcomplete python-darkdetect
```

**Step 2 — clone and install:**

```bash
git clone https://github.com/Axel-DaMage/LenovoLegionLinux.git && cd LenovoLegionLinux && bash install.sh
```

Reboot after installation. Then launch with:

```bash
legion_gui
```

## Uninstall

```bash
sudo dkms remove LenovoLegionLinux/1.0.0 --all
sudo pip uninstall legion_linux --break-system-packages
```

## License

GPL-2.0
