import html
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from config import DIAS_SEMANA_ORDEM, FUSO_BR

def agora_br() -> datetime:
    return datetime.now(FUSO_BR)

def hoje_br() -> date:
    return agora_br().date()

def sanitizar_html(texto: str) -> str:
    return html.escape(str(texto or ""), quote=True)

def saudacao_horario() -> str:
    hora = agora_br().hour
    if 5 <= hora < 12:
        return "Bom dia"
    elif 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"

def obter_proxima_prova(provas: list) -> dict | None:
    hoje = hoje_br()
    futuras = []
    for p in provas:
        try:
            dt_prova = date.fromisoformat(p["data"])
            dias_restantes = (dt_prova - hoje).days
            if dias_restantes >= 0:
                futuras.append({**p, "dias_restantes": dias_restantes})
        except Exception:
            continue
    if not futuras:
        return None
    futuras.sort(key=lambda x: x["dias_restantes"])
    return futuras[0]

def calcular_fase_periodizacao(dias_restantes: int) -> tuple[str, str]:
    if dias_restantes > 56:
        return "Fase de Base", "Construindo resistência aeróbica e consistência sem pressa."
    elif dias_restantes > 21:
        return "Fase de Construção", "Aumentando o ritmo e o volume específico para a prova."
    elif dias_restantes > 7:
        return "Fase de Pico", "Ajustes finais de intensidade no ritmo da prova."
    else:
        return "Semana de Polimento", "Reduzindo o volume para você chegar leve e descansado no dia."

def resumo_provas_para_ia(provas: list) -> str:
    hoje = hoje_br()
    linhas = []
    for p in sorted(provas, key=lambda x: x.get("data", "")):
        try:
            dt = date.fromisoformat(p["data"])
            dias = (dt - hoje).days
            if dias >= 0:
                fase, orientacao = calcular_fase_periodizacao(dias)
                linhas.append(
                    f"- {p['nome']} ({p['modalidade']}) em {dt.strftime('%d/%m/%Y')} "
                    f"(faltam {dias} dias | {fase}: {orientacao})"
                )
        except Exception:
            continue
    return "\n".join(linhas) if linhas else "Nenhuma prova cadastrada no momento (foco em evolução contínua)."

def gerar_texto_whatsapp(usuario: str, semana: int, planilha: list) -> str:
    linhas = [f"🏃 *MEUS TREINOS — SEMANA {semana}* ({usuario.capitalize()})", ""]
    for item in planilha:
        status = "✅" if item.get("concluido") else "⬜"
        if item.get("modalidade", "").lower() == "descanso":
            linhas.append(f"😴 *{item['dia']}:* Descanso")
        else:
            linhas.append(
                f"{status} *{item['dia']} — {item['modalidade']} ({item['titulo']})*\n"
                f"   📏 {item['duracao_ou_dist']}\n"
                f"   📝 {item['descricao']}"
            )
        linhas.append("")
    return "\n".join(linhas)

def escapar_texto_ics(texto: str) -> str:
    return (
        str(texto or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )

def gerar_arquivo_ics(usuario: str, semana: int, planilha: list) -> str:
    agora = agora_br()
    agora_utc = agora.astimezone(ZoneInfo("UTC"))
    hoje = agora.date()

    # Se hoje é segunda (weekday == 0), usa esta semana; caso contrário, próxima segunda
    dias_ate_segunda = (7 - hoje.weekday()) % 7
    base_segunda = hoje + timedelta(days=dias_ate_segunda)

    eventos = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Treinador Pessoal//PT-BR//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]

    for idx, item in enumerate(planilha):
        if item.get("modalidade", "").lower() == "descanso":
            continue

        dia_nome = item.get("dia", "")
        offset = idx
        for i, d in enumerate(DIAS_SEMANA_ORDEM):
            if d.lower() in dia_nome.lower():
                offset = i
                break

        data_treino = base_segunda + timedelta(days=offset)
        dt_inicio = data_treino.strftime("%Y%m%dT070000")
        dt_fim = data_treino.strftime("%Y%m%dT080000")
        uid = f"treinador-{usuario}-s{semana}-{idx}-{int(agora.timestamp())}@treinador"

        summary = escapar_texto_ics(f"[{item['modalidade']}] {item['titulo']} ({item['duracao_ou_dist']})")
        desc = escapar_texto_ics(item["descricao"])

        eventos.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{agora_utc.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;TZID=America/Sao_Paulo:{dt_inicio}",
            f"DTEND;TZID=America/Sao_Paulo:{dt_fim}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT"
        ])

    eventos.append("END:VCALENDAR")
    return "\r\n".join(eventos)
