import subprocess

from src.ui.constants import VPN_SYSTEMD_UNITS, VPN_SYSTEMD_UNIT_SET


def get_vpn_systemd_states():
    """Состояние ActiveState через systemctl is-active для каждого unit."""
    rows = []
    for unit, label, kind in VPN_SYSTEMD_UNITS:
        state = "unknown"
        try:
            completed = subprocess.run(
                ["/bin/systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=8,
            )
            st = (completed.stdout or "").strip()
            if st:
                state = st
            else:
                load = subprocess.run(
                    ["/bin/systemctl", "show", "-p", "LoadState", "--value", unit],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if (load.stdout or "").strip() == "not-found":
                    state = "not-found"
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            state = "unknown"
        rows.append(
            {
                "unit": unit,
                "label": label,
                "kind": kind,
                "state": state,
            }
        )
    return rows


def restart_vpn_systemd_unit(unit: str) -> tuple[bool, str]:
    """Перезапуск unit из белого списка VPN."""
    if unit not in VPN_SYSTEMD_UNIT_SET:
        return False, "unknown unit"
    try:
        completed = subprocess.run(
            ["/bin/systemctl", "restart", unit],
            capture_output=True,
            text=True,
            timeout=120,
        )
        err = (completed.stderr or completed.stdout or "").strip()
        if completed.returncode != 0:
            return False, err[:500] if err else "systemctl restart failed"
        return True, "ok"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return False, str(e)
