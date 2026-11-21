import hashlib
import math
import xml.etree.ElementTree as ET
from datetime import datetime
from config import MAX_UPLOAD_BYTES

try:
    from fitparse import FitFile
    HAS_FITPARSE = True
except ImportError:
    HAS_FITPARSE = False


def _short_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _fmt_duration(seconds: float) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}min" if h > 0 else f"{m}min{s:02d}s"


def _fmt_pace(seconds: float, km: float) -> str:
    if km <= 0.05 or seconds <= 0:
        return ""
    pace_s = seconds / km
    m = int(pace_s // 60)
    s = int(round(pace_s % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}/km"


def _safe_xml_root(raw_bytes: bytes) -> ET.Element:
    head = raw_bytes[:2048].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError("Arquivo XML rejeitado por conter declarações externas não permitidas.")
    return ET.fromstring(raw_bytes)


def parse_activity_file(uploaded_file) -> tuple[str, str]:
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ValueError("Arquivo muito grande. O limite máximo é 5 MB.")

    filename = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()
    file_hash = _short_hash(raw)

    if filename.endswith(".fit"):
        if not HAS_FITPARSE:
            raise ValueError("Suporte a arquivos .fit indisponível no momento.")
        fit = FitFile(raw)
        dist_m = 0.0
        time_s = 0.0
        avg_hr = None
        sport = "Atividade"

        for rec in fit.get_messages("session"):
            vals = {d.name: d.value for d in rec}
            if vals.get("total_distance"):
                dist_m = float(vals["total_distance"])
            if vals.get("total_timer_time"):
                time_s = float(vals["total_timer_time"])
            elif vals.get("total_elapsed_time"):
                time_s = float(vals["total_elapsed_time"])
            if vals.get("avg_heart_rate"):
                avg_hr = int(vals["avg_heart_rate"])
            if vals.get("sport"):
                sport = str(vals["sport"]).capitalize()

        if dist_m == 0 and time_s == 0:
            raise ValueError("Nenhuma sessão válida encontrada neste arquivo .fit.")

        km = dist_m / 1000.0
        parts = [sport]
        if km > 0:
            parts.append(f"{km:.2f} km")
        if time_s > 0:
            parts.append(f"Tempo: {_fmt_duration(time_s)}")
        pace = _fmt_pace(time_s, km)
        if pace:
            parts.append(f"Ritmo: {pace}")
        if avg_hr:
            parts.append(f"FC média: {avg_hr} bpm")
        return " | ".join(parts), file_hash

    if filename.endswith(".tcx"):
        root = _safe_xml_root(raw)
        hrs = []
        lap_dists = []
        lap_times = []

        for elem in root.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "Value" and elem.text and elem.text.isdigit():
                hrs.append(int(elem.text))
            elif elem.tag.endswith("Lap"):
                for child in elem:
                    if child.tag.endswith("DistanceMeters") and child.text:
                        lap_dists.append(float(child.text))
                    elif child.tag.endswith("TotalTimeSeconds") and child.text:
                        lap_times.append(float(child.text))

        km = sum(lap_dists) / 1000.0
        time_s = sum(lap_times)
        parts = ["Garmin/Strava (.tcx)"]
        if km > 0:
            parts.append(f"{km:.2f} km")
        if time_s > 0:
            parts.append(f"Tempo: {_fmt_duration(time_s)}")
        pace = _fmt_pace(time_s, km)
        if pace:
            parts.append(f"Ritmo: {pace}")
        if hrs:
            parts.append(f"FC média: {int(sum(hrs) / len(hrs))} bpm")
        return " | ".join(parts), file_hash

    if filename.endswith(".gpx"):
        root = _safe_xml_root(raw)
        coords = []
        timestamps = []

        for elem in root.iter():
            if elem.tag.endswith("trkpt"):
                coords.append((float(elem.attrib["lat"]), float(elem.attrib["lon"])))
                for child in elem:
                    if child.tag.endswith("time") and child.text:
                        try:
                            timestamps.append(datetime.fromisoformat(child.text.replace("Z", "+00:00")))
                        except ValueError:
                            pass

        km = 0.0
        for idx in range(1, len(coords)):
            lat1, lon1 = map(math.radians, coords[idx - 1])
            lat2, lon2 = map(math.radians, coords[idx])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            km += 6371.0 * 2 * math.asin(math.sqrt(a))

        time_s = (timestamps[-1] - timestamps[0]).total_seconds() if len(timestamps) >= 2 else 0.0
        parts = ["Strava/GPS (.gpx)"]
        if km > 0:
            parts.append(f"{km:.2f} km")
        if time_s > 0:
            parts.append(f"Tempo: {_fmt_duration(time_s)}")
        pace = _fmt_pace(time_s, km)
        if pace:
            parts.append(f"Ritmo: {pace}")
        return " | ".join(parts), file_hash

    raise ValueError("Formato inválido. Envie apenas .fit, .tcx ou .gpx.")
