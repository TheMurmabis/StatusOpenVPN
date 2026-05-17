import os
import re

from src.ui.constants import OPENVPN_CONFIG_PATHS


_OVPN_FILE_STEM_CORE = re.compile(
    r"^(?:antizapret|vpn)-(?:udp|tcp|udp-only|tcp-only)-(.+)-\([^)]+\)$",
    re.IGNORECASE,
)
_OVPN_FILE_STEM_SIMPLE = re.compile(
    r"^(?:antizapret|vpn)-(?:udp|tcp|udp-only|tcp-only)-(.+)$",
    re.IGNORECASE,
)


def extract_client_name_from_ovpn(filename):
    name = os.path.splitext(filename)[0]
    suffixes = ["-udp", "-tcp", "-udp-only", "-tcp-only"]
    for suffix in suffixes:
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break

    lowered = name.lower()
    for prefix in ("antizapret-", "vpn-"):
        if lowered.startswith(prefix):
            name = name[len(prefix):]
            break

    return name.strip() or None


def openvpn_client_identity_variants(name):
    """Варианты строки имени клиента (логи, CN, короткое имя) для сопоставления с файлом."""
    if not name:
        return set()
    n = name.strip()
    out = {n, n.lower()}
    no_ip = re.sub(r"\s*\([^)]*\)\s*$", "", n).strip()
    if no_ip:
        out.add(no_ip)
        out.add(no_ip.lower())
    c = n
    for _ in range(8):
        low = c.lower()
        if low.startswith("antizapret-"):
            c = c[11:]
        elif low.startswith("vpn-"):
            c = c[4:]
        else:
            break
        out.add(c)
        out.add(c.lower())
        no_ip2 = re.sub(r"\s*\([^)]*\)\s*$", "", c).strip()
        if no_ip2:
            out.add(no_ip2)
            out.add(no_ip2.lower())
    for _ in range(4):
        added = False
        for x in list(out):
            low = x.lower()
            for p in ("udp-", "tcp-", "udp-only-", "tcp-only-"):
                if low.startswith(p):
                    x2 = x[len(p):].strip()
                    if x2 and x2 not in out:
                        out.add(x2)
                        out.add(x2.lower())
                        added = True
        if not added:
            break
    return {x for x in out if x}


def openvpn_filename_identity_variants(stem):
    """Варианты идентификатора из имени файла без расширения."""
    if not stem:
        return set()
    out = {stem, stem.lower()}
    legacy = extract_client_name_from_ovpn(stem + ".ovpn")
    if legacy:
        out.add(legacy)
        out.add(legacy.lower())
    m = _OVPN_FILE_STEM_CORE.match(stem)
    if m:
        g = m.group(1).strip()
        out.add(g)
        out.add(g.lower())
    else:
        m2 = _OVPN_FILE_STEM_SIMPLE.match(stem)
        if m2:
            g = m2.group(1).strip()
            out.add(g)
            out.add(g.lower())
    m3 = re.match(r"^(?:antizapret|vpn)-(.+)-\([^)]+\)$", stem, re.IGNORECASE)
    if m3:
        g = m3.group(1).strip()
        out.add(g)
        out.add(g.lower())
    return {x for x in out if x}


def openvpn_client_name_matches_ovpn_file(client_name, filename):
    """Имя клиента из UI совпадает с .ovpn (полный CN, короткое имя)."""
    if not filename.endswith(".ovpn"):
        return False
    stem = os.path.splitext(filename)[0]
    ca = openvpn_client_identity_variants(client_name)
    fb = openvpn_filename_identity_variants(stem)
    if ca & fb:
        return True
    cal = {x.lower() for x in ca}
    fbl = {x.lower() for x in fb}
    if cal & fbl:
        return True
    clean = (client_name or "").replace("antizapret-", "").replace("vpn-", "")
    if len(clean) >= 3 and clean in stem:
        return True
    return False


def list_openvpn_ovpn_paths_for_client(client_name):
    """Пути к .ovpn файлам клиента."""
    clean = (client_name or "").strip()
    if not clean:
        return []
    matches = []
    for base_dir in OPENVPN_CONFIG_PATHS:
        if not os.path.isdir(base_dir):
            continue
        for root, _, files in os.walk(base_dir):
            for filename in files:
                if not filename.endswith(".ovpn"):
                    continue
                if openvpn_client_name_matches_ovpn_file(clean, filename):
                    matches.append(os.path.join(root, filename))
    matches.sort()
    return matches


def ovpn_profile_label(full_path):
    """Краткая подпись профиля для UI."""
    basename = os.path.basename(full_path)
    parent = os.path.basename(os.path.dirname(full_path))
    if parent:
        return f"{basename} ({parent})"
    return basename


def clean_client_display_name(client_name, server_ip):
    if not client_name:
        return client_name

    if not server_ip or not isinstance(server_ip, str):
        return client_name

    ip_pattern = re.escape(server_ip)
    client_name = re.sub(
        rf"[\s@\-\(\[]*{ip_pattern}(?::\d+)?[\)\]]*",
        "",
        client_name,
    )

    return client_name.strip()
