import html
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
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


def build_races_context(provas: list[dict]) -> str:
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
