import html
import re
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from fpdf import FPDF
from config import DIAS_SEMANA, TZ_BR


def now_br() -> datetime:
    return datetime.now(TZ_BR)


def today_br() -> date:
    return now_br().date()


def esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def greeting_br() -> str:
    hour = now_br().hour
    if 5 <= hour < 12:
        return "Bom dia"
    if 12 <= hour < 18:
        return "Boa tarde"
    return "Boa noite"


def get_next_race(provas: list[dict]) -> dict | None:
    today = today_br()
    upcoming = []
    for p in provas:
        try:
            race_dt = date.fromisoformat(p["data"])
            diff = (race_dt - today).days
            if diff >= 0:
                upcoming.append({**p, "dias_restantes": diff})
        except Exception:
            continue
    upcoming.sort(key=lambda x: x["dias_restantes"])
    return upcoming[0] if upcoming else None


def get_periodization_phase(days_left: int) -> tuple[str, str]:
    if days_left > 56:
        return "Fase de Base", "Construindo resistência aeróbica e consistência sem pressa."
    if days_left > 21:
        return "Fase de Construção", "Aumentando o ritmo e o volume específico para a prova."
    if days_left > 7:
        return "Fase de Pico", "Ajustes finais de intensidade no ritmo da prova."
    return "Semana de Polimento", "Reduzindo o volume para você chegar leve e descansado no dia."


def parse_time_to_seconds(time_str: str) -> int | None:
    raw = str(time_str or "").strip().lower()
    if not raw:
        return None

    colon_parts = re.findall(r"\d+", raw)
    if ":" in raw and len(colon_parts) in (2, 3):
        nums = [int(x) for x in colon_parts]
        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        return nums[0] * 3600 + nums[1] * 60 + nums[2]

    h_match = re.search(r"(\d+)\s*h", raw)
    m_match = re.search(r"(\d+)\s*(?:m|min)", raw)
    s_match = re.search(r"(\d+)\s*(?:s|seg)", raw)
    if h_match or m_match:
        h = int(h_match.group(1)) if h_match else 0
        m = int(m_match.group(1)) if m_match else 0
        s = int(s_match.group(1)) if s_match else 0
        return h * 3600 + m * 60 + s

    return None


def _extract_distance_km(text: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*km", str(text or "").lower())
    if m:
        return float(m.group(1).replace(",", "."))
    if "meia maratona" in str(text or "").lower() or "21k" in str(text or "").lower():
        return 21.1
    if "maratona" in str(text or "").lower() or "42k" in str(text or "").lower():
        return 42.2
    if "10k" in str(text or "").lower():
        return 10.0
    if "5k" in str(text or "").lower():
        return 5.0
    return None


def _fmt_pace_sec(sec_per_km: float) -> str:
    total = int(round(sec_per_km))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}/km"


def compute_pace_zones(perfil: dict, provas: list[dict]) -> dict | None:
    """Calcula zonas de ritmo (Z1-Z5) a partir do melhor tempo de prova ou tempo base 5km."""
    best_5k_eq_sec = None
    fonte = ""

    # 1. Tenta extrair das provas realizadas com tempo oficial
    for p in provas:
        tempo_s = parse_time_to_seconds(p.get("tempo_prova", ""))
        dist_km = _extract_distance_km(f"{p.get('nome', '')} {p.get('modalidade', '')}")
        if tempo_s and dist_km and dist_km >= 1.0:
            # Fórmula de Riegel para equivalência nos 5 km
            eq_5k = tempo_s * ((5.0 / dist_km) ** 1.06)
            if best_5k_eq_sec is None or eq_5k < best_5k_eq_sec:
                best_5k_eq_sec = eq_5k
                fonte = f"{p.get('nome')} ({p.get('tempo_prova')})"

    # 2. Fallback para tempo base de 5km salvo no perfil
    if best_5k_eq_sec is None and perfil.get("tempo_5k"):
        t_perfil = parse_time_to_seconds(perfil["tempo_5k"])
        if t_perfil and t_perfil >= 600:
            best_5k_eq_sec = float(t_perfil)
            fonte = f"Base 5 km ({perfil['tempo_5k']})"

    if not best_5k_eq_sec:
        return None

    pace_5k = best_5k_eq_sec / 5.0
    return {
        "fonte": fonte,
        "Z1 (Regenerativo)": f"{_fmt_pace_sec(pace_5k * 1.24)} – {_fmt_pace_sec(pace_5k * 1.32)}",
        "Z2 (Base Aeróbica)": f"{_fmt_pace_sec(pace_5k * 1.14)} – {_fmt_pace_sec(pace_5k * 1.23)}",
        "Z3 (Ritmo / Tempo)": f"{_fmt_pace_sec(pace_5k * 1.05)} – {_fmt_pace_sec(pace_5k * 1.12)}",
        "Z4 (Limiar)": f"{_fmt_pace_sec(pace_5k * 0.99)} – {_fmt_pace_sec(pace_5k * 1.04)}",
        "Z5 (Tiros / VO2)": f"{_fmt_pace_sec(pace_5k * 0.91)} – {_fmt_pace_sec(pace_5k * 0.98)}",
    }


def build_races_context(provas: list[dict], zonas: dict | None = None) -> str:
    today = today_br()
    upcoming = []
    completed = []

    for p in sorted(provas, key=lambda x: x.get("data", "")):
        try:
            dt = date.fromisoformat(p["data"])
            diff = (dt - today).days
            if diff >= 0:
                phase, guidance = get_periodization_phase(diff)
                upcoming.append(
                    f"- [ALVO] {p['nome']} ({p['modalidade']}) em {dt.strftime('%d/%m/%Y')} "
                    f"(faltam {diff} dias | {phase}: {guidance})"
                )
            else:
                time_str = f" | Tempo oficial: {p['tempo_prova']}" if p.get("tempo_prova") else ""
                pr_str = " (PR / Recorde Pessoal!)" if p.get("eh_pr") else ""
                completed.append(
                    f"- [REALIZADA] {p['nome']} ({p['modalidade']}) em {dt.strftime('%d/%m/%Y')}{time_str}{pr_str}"
                )
        except Exception:
            continue

    blocks = []
    if upcoming:
        blocks.append("Próximas provas alvo:\n" + "\n".join(upcoming))
    else:
        blocks.append("Nenhuma prova futura cadastrada no momento (foco em evolução contínua).")

    if completed:
        blocks.append("Histórico de provas já realizadas pelo aluno:\n" + "\n".join(completed))

    if zonas:
        z_lines = [f"- {k}: {v}" for k, v in zonas.items() if k != "fonte"]
        blocks.append(f"Zonas de ritmo calculadas ({zonas['fonte']}):\n" + "\n".join(z_lines))

    return "\n\n".join(blocks)


def format_whatsapp_plan(usuario: str, semana: int, planilha: list[dict]) -> str:
    lines = [f"🏃 *MEUS TREINOS — SEMANA {semana}* ({usuario.capitalize()})", ""]
    for item in planilha:
        done = "✅" if item.get("concluido") else "⬜"
        if item.get("modalidade", "").lower() == "descanso":
            lines.append(f"😴 *{item['dia']}:* Descanso")
        else:
            lines.append(
                f"{done} *{item['dia']} — {item['modalidade']} ({item['titulo']})*\n"
                f"   📏 {item['duracao_ou_dist']}\n"
                f"   📝 {item['descricao']}"
            )
        lines.append("")
    return "\n".join(lines)


def _latin1_safe(text: str) -> str:
    return str(text or "").encode("latin-1", errors="replace").decode("latin-1")


def build_plan_pdf(usuario: str, semana: int, perfil: dict, planilha: list[dict], feedback_semana: str = "") -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _latin1_safe(f"Plano de Treino - Semana {semana} ({usuario.capitalize()})"), ln=True)

    pdf.set_font("Helvetica", "", 10)
    esporte = perfil.get("esporte", "Treino Personalizado")
    objetivo = perfil.get("objetivo", "Evolução contínua")
    pdf.cell(0, 6, _latin1_safe(f"Modalidade: {esporte} | Objetivo: {objetivo}"), ln=True)
    pdf.ln(3)

    if feedback_semana:
        pdf.set_fill_color(245, 245, 245)
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(0, 5, _latin1_safe(f"Nota do Treinador: {feedback_semana}"), fill=True)
        pdf.ln(4)

    for item in planilha:
        is_rest = item.get("modalidade", "").lower() == "descanso"
        status = "[FEITO] " if item.get("concluido") else ""
        header = f"{status}{item['dia']} - {item['modalidade']}: {item['titulo']} ({item['duracao_ou_dist']})"

        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, _latin1_safe(header), ln=True)

        if not is_rest:
            pdf.set_font("Helvetica", "", 9.5)
            pdf.multi_cell(0, 5, _latin1_safe(item.get("descricao", "")))
            if item.get("dados_arquivo"):
                pdf.set_font("Helvetica", "I", 8.5)
                pdf.cell(0, 5, _latin1_safe(f"Relógio: {item['dados_arquivo']}"), ln=True)
        pdf.ln(2)

    return bytes(pdf.output())


def _escape_ics(text: str) -> str:
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def build_ics_calendar(usuario: str, semana: int, planilha: list[dict]) -> str:
    now = now_br()
    now_utc = now.astimezone(ZoneInfo("UTC"))
    today = now.date()

    days_to_monday = (7 - today.weekday()) % 7
    monday = today + timedelta(days=days_to_monday)

    events = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Treinador Pessoal//PT-BR//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]

    for idx, item in enumerate(planilha):
        if item.get("modalidade", "").lower() == "descanso":
            continue

        day_name = item.get("dia", "")
        offset = idx
        for i, d in enumerate(DIAS_SEMANA):
            if d.lower() in day_name.lower():
                offset = i
                break

        workout_date = monday + timedelta(days=offset)
        dt_start = workout_date.strftime("%Y%m%dT070000")
        dt_end = workout_date.strftime("%Y%m%dT080000")
        uid = f"treinador-{usuario}-s{semana}-{idx}-{int(now.timestamp())}@treinador"

        summary = _escape_ics(f"[{item['modalidade']}] {item['titulo']} ({item['duracao_ou_dist']})")
        desc = _escape_ics(item["descricao"])

        events.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_utc.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;TZID=America/Sao_Paulo:{dt_start}",
            f"DTEND;TZID=America/Sao_Paulo:{dt_end}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT"
        ])

    events.append("END:VCALENDAR")
    return "\r\n".join(events)
