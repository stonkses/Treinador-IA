import hashlib
import math
import xml.etree.ElementTree as ET
from datetime import datetime

try:
    from fitparse import FitFile
    TEM_FITPARSE = True
except ImportError:
    TEM_FITPARSE = False

def calcular_hash_bytes(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()[:16]

def formatar_tempo(segundos: float) -> str:
    seg = int(round(segundos))
    horas = seg // 3600
    minutos = (seg % 3600) // 60
    s = seg % 60
    if horas > 0:
        return f"{horas}h{minutos:02d}min"
    return f"{minutos}min{s:02d}s"

def formatar_pace(segundos: float, distancia_km: float) -> str:
    if distancia_km <= 0.05 or segundos <= 0:
        return ""
    pace_seg = segundos / distancia_km
    m = int(pace_seg // 60)
    s = int(round(pace_seg % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}/km"

def processar_arquivo_atividade(uploaded_file) -> tuple[str, str]:
    nome = uploaded_file.name.lower()
    conteudo_bytes = uploaded_file.getvalue()
    arq_hash = calcular_hash_bytes(conteudo_bytes)

    if nome.endswith(".fit"):
        if not TEM_FITPARSE:
            raise ValueError("A biblioteca fitparse ainda não está instalada no servidor.")
        fitfile = FitFile(conteudo_bytes)
        dist_m = 0.0
        tempo_s = 0.0
        fc_media = None
        esporte = "Atividade"

        for record in fitfile.get_messages("session"):
            vals = {d.name: d.value for d in record}
            if vals.get("total_distance"):
                dist_m = float(vals["total_distance"])
            if vals.get("total_timer_time"):
                tempo_s = float(vals["total_timer_time"])
            elif vals.get("total_elapsed_time"):
                tempo_s = float(vals["total_elapsed_time"])
            if vals.get("avg_heart_rate"):
                fc_media = int(vals["avg_heart_rate"])
            if vals.get("sport"):
                esporte = str(vals["sport"]).capitalize()

        if dist_m == 0 and tempo_s == 0:
            raise ValueError("Não encontrei dados de sessão dentro deste arquivo .fit.")

        dist_km = dist_m / 1000.0
        partes = [f"{esporte}"]
        if dist_km > 0:
            partes.append(f"{dist_km:.2f} km")
        if tempo_s > 0:
            partes.append(f"Tempo: {formatar_tempo(tempo_s)}")
        pace = formatar_pace(tempo_s, dist_km)
        if pace:
            partes.append(f"Ritmo: {pace}")
        if fc_media:
            partes.append(f"FC média: {fc_media} bpm")
        return " | ".join(partes), arq_hash

    elif nome.endswith(".tcx"):
        root = ET.fromstring(conteudo_bytes)
        fcs = []
        laps_dist = []
        laps_time = []

        for elem in root.iter():
            tag = elem.tag.split("}")[-1]
            if tag == "Value" and elem.text and elem.text.isdigit():
                fcs.append(int(elem.text))
            elif elem.tag.endswith("Lap"):
                for child in elem:
                    if child.tag.endswith("DistanceMeters") and child.text:
                        laps_dist.append(float(child.text))
                    elif child.tag.endswith("TotalTimeSeconds") and child.text:
                        laps_time.append(float(child.text))

        dist_m = sum(laps_dist)
        tempo_s = sum(laps_time)
        dist_km = dist_m / 1000.0

        partes = ["Garmin/Strava (.tcx)"]
        if dist_km > 0:
            partes.append(f"{dist_km:.2f} km")
        if tempo_s > 0:
            partes.append(f"Tempo: {formatar_tempo(tempo_s)}")
        pace = formatar_pace(tempo_s, dist_km)
        if pace:
            partes.append(f"Ritmo: {pace}")
        if fcs:
            partes.append(f"FC média: {int(sum(fcs)/len(fcs))} bpm")
        return " | ".join(partes), arq_hash

    elif nome.endswith(".gpx"):
        root = ET.fromstring(conteudo_bytes)
        pontos = []
        tempos = []
        for elem in root.iter():
            if elem.tag.endswith("trkpt"):
                lat = float(elem.attrib["lat"])
                lon = float(elem.attrib["lon"])
                pontos.append((lat, lon))
                for child in elem:
                    if child.tag.endswith("time") and child.text:
                        try:
                            tempos.append(datetime.fromisoformat(child.text.replace("Z", "+00:00")))
                        except Exception:
                            pass

        dist_km = 0.0
        for idx in range(1, len(pontos)):
            lat1, lon1 = map(math.radians, pontos[idx - 1])
            lat2, lon2 = map(math.radians, pontos[idx])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            dist_km += 6371.0 * 2 * math.asin(math.sqrt(a))

        tempo_s = (tempos[-1] - tempos[0]).total_seconds() if len(tempos) >= 2 else 0.0
        partes = ["Strava/GPS (.gpx)"]
        if dist_km > 0:
            partes.append(f"{dist_km:.2f} km")
        if tempo_s > 0:
            partes.append(f"Tempo: {formatar_tempo(tempo_s)}")
        pace = formatar_pace(tempo_s, dist_km)
        if pace:
            partes.append(f"Ritmo: {pace}")
        return " | ".join(partes), arq_hash

    raise ValueError("Formato não suportado. Envie um arquivo .fit, .tcx ou .gpx.")
