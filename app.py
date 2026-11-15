import streamlit as st
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from google import genai
from supabase import create_client, Client

try:
    from fitparse import FitFile
    TEM_FITPARSE = True
except ImportError:
    TEM_FITPARSE = False

# ==========================================
# CONFIGURAÇÃO DA PÁGINA E VERSÃO
# ==========================================
VERSAO_APP = "v2.0"

st.set_page_config(
    page_title="Treinador • Seu Plano de Treino",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# CSS CUSTOMIZADO (VISUAL HUMANO, SUAVE E MINIMALISTA)
# ==========================================
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background: transparent !important;}

    .stApp {
        background-color: #0F141E;
        color: #E2E8F0;
    }

    /* Saudação e Cabeçalho Orgânico */
    .welcome-card {
        background: linear-gradient(135deg, #171E2E 0%, #1D2638 100%);
        border: 1px solid #28334A;
        border-radius: 18px;
        padding: 24px 28px;
        margin-bottom: 20px;
    }
    .welcome-title {
        font-size: 1.75rem;
        font-weight: 700;
        color: #F8FAFC;
        margin: 0;
        letter-spacing: -0.3px;
    }
    .welcome-sub {
        font-size: 0.98rem;
        color: #94A3B8;
        margin-top: 8px;
        line-height: 1.5;
    }
    .pill-fase {
        display: inline-block;
        background-color: rgba(249, 115, 22, 0.14);
        color: #FB923C;
        border: 1px solid rgba(249, 115, 22, 0.35);
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-top: 10px;
    }

    /* Cartões de Métricas Minimalistas */
    div[data-testid="stMetric"] {
        background-color: #161D2C;
        border: 1px solid #253046;
        border-radius: 16px;
        padding: 16px 20px;
    }
    div[data-testid="stMetric"] label {
        color: #94A3B8 !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        text-transform: none !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #F8FAFC !important;
        font-size: 1.55rem !important;
        font-weight: 700 !important;
    }

    /* Cartões dos Treinos */
    div[data-testid="stExpander"] {
        background-color: #161D2C !important;
        border: 1px solid #253046 !important;
        border-radius: 16px !important;
        margin-bottom: 12px !important;
        transition: all 0.2s ease;
    }
    div[data-testid="stExpander"]:hover {
        border-color: #475569 !important;
    }

    /* Abas */
    button[data-baseweb="tab"] {
        font-weight: 500 !important;
        font-size: 0.95rem !important;
        padding: 10px 16px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #FB923C !important;
        font-weight: 600 !important;
    }

    /* Botões */
    .stButton > button[kind="primary"] {
        background-color: #F97316 !important;
        border: none !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border-radius: 12px !important;
        padding: 0.6rem 1.2rem !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #EA580C !important;
    }
    .stButton > button[kind="secondary"] {
        border-radius: 12px !important;
        border: 1px solid #2D3B55 !important;
        background-color: #1A2234 !important;
        color: #E2E8F0 !important;
    }
</style>
""", unsafe_allow_html=True)

DIAS_SEMANA_ORDEM = [
    "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"
]

SENSAÇÕES_OPCOES = [
    "Ainda não fiz",
    "Leve e tranquilo",
    "Na medida certa",
    "Pesado, mas deu",
    "Exausto / Muito difícil"
]

# ==========================================
# CONEXÕES (SUPABASE E GEMINI)
# ==========================================
@st.cache_resource
def get_supabase_client() -> Client | None:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

def gerar_resposta_ia(prompt: str) -> str:
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        raise ValueError("Chave GEMINI_API_KEY não encontrada nas configurações.")

    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

    modelos_disponiveis = []
    try:
        for m in client.models.list():
            nome = m.name.replace("models/", "")
            if "gemini" in nome and "embedding" not in nome and "imagen" not in nome:
                modelos_disponiveis.append(nome)
    except Exception:
        pass

    preferidos = [
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.1-pro-preview",
    ]
    candidatos = [m for m in preferidos if m in modelos_disponiveis] + [
        m for m in modelos_disponiveis if m not in preferidos
    ]
    if not candidatos:
        candidatos = preferidos

    erros = []
    for modelo in candidatos[:5]:
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=prompt
            )
            return response.text
        except Exception as e:
            erros.append(f"{modelo}: {e}")
            continue
    raise RuntimeError(" | ".join(erros))

# ==========================================
# PERSISTÊNCIA E NORMALIZAÇÃO
# ==========================================
def estrutura_padrao():
    return {
        "perfil": {},
        "semana_atual": 1,
        "planilha": [],
        "historico": [],
        "provas": []
    }

def parse_bool_seguro(valor) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.strip().lower() in ("true", "1", "sim", "yes", "s", "concluido", "concluído")
    return bool(valor)

def normalizar_item_treino(item: dict) -> dict:
    sensacao_salva = str(item.get("sensacao", ""))
    if not sensacao_salva and item.get("rpe_real"):
        rpe_antigo = int(item.get("rpe_real", 0))
        if rpe_antigo <= 4:
            sensacao_salva = "Leve e tranquilo"
        elif rpe_antigo <= 7:
            sensacao_salva = "Na medida certa"
        elif rpe_antigo <= 9:
            sensacao_salva = "Pesado, mas deu"
        else:
            sensacao_salva = "Exausto / Muito difícil"

    return {
        "dia": str(item.get("dia", "Dia")),
        "modalidade": str(item.get("modalidade") or item.get("esporte") or item.get("tipo") or "Treino"),
        "titulo": str(item.get("titulo") or item.get("treino") or item.get("foco") or "Sessão"),
        "descricao": str(item.get("descricao") or item.get("detalhes") or item.get("prescricao") or ""),
        "duracao_ou_dist": str(item.get("duracao_ou_dist") or item.get("volume") or item.get("duracao") or "-"),
        "concluido": parse_bool_seguro(item.get("concluido", False)),
        "sensacao": sensacao_salva if sensacao_salva in SENSAÇÕES_OPCOES else "Ainda não fiz",
        "feedback": str(item.get("feedback", "")),
        "dados_arquivo": str(item.get("dados_arquivo", ""))
    }

def carregar_dados_usuario(usuario: str) -> dict:
    sb = get_supabase_client()
    if not sb:
        return estrutura_padrao()
    try:
        resp = sb.table("atletas").select("dados").eq("usuario", usuario).execute()
        if resp.data and len(resp.data) > 0:
            dados = resp.data[0].get("dados") or {}
            base = estrutura_padrao()
            base.update(dados)
            if base.get("planilha"):
                base["planilha"] = [normalizar_item_treino(t) for t in base["planilha"]]
            if "provas" not in base or base["provas"] is None:
                base["provas"] = []
            return base
    except Exception as e:
        st.error(f"Não consegui carregar seus dados agora: {e}")
    return estrutura_padrao()

def salvar_dados_usuario(usuario: str, dados: dict):
    sb = get_supabase_client()
    if not sb:
        return
    try:
        sb.table("atletas").upsert({
            "usuario": usuario,
            "dados": dados
        }).execute()
    except Exception as e:
        st.error(f"Não consegui salvar suas alterações: {e}")

# ==========================================
# CALENDÁRIO DE PROVAS & PERIODIZAÇÃO
# ==========================================
def obter_proxima_prova(provas: list) -> dict | None:
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
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
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
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

# ==========================================
# LEITURA DE ARQUIVOS GARMIN / STRAVA (.FIT, .TCX, .GPX)
# ==========================================
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

def processar_arquivo_atividade(uploaded_file) -> str:
    nome = uploaded_file.name.lower()
    conteudo_bytes = uploaded_file.getvalue()

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
        return " | ".join(partes)

    elif nome.endswith(".tcx"):
        root = ET.fromstring(conteudo_bytes)
        dist_m = 0.0
        tempo_s = 0.0
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

        if laps_dist:
            dist_m = sum(laps_dist)
        if laps_time:
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
        return " | ".join(partes)

    elif nome.endswith(".gpx"):
        import math
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
        return " | ".join(partes)

    raise ValueError("Formato não suportado. Envie um arquivo .fit, .tcx ou .gpx.")

# ==========================================
# UTILITÁRIOS DE PLANILHA E EXPORTAÇÃO
# ==========================================
def extrair_json_planilha(texto: str) -> list:
    texto_limpo = re.sub(r"```json\s*", "", texto, flags=re.IGNORECASE)
    texto_limpo = re.sub(r"```\s*", "", texto_limpo).strip()
    inicio = texto_limpo.find("[")
    fim = texto_limpo.rfind("]")
    if inicio != -1 and fim != -1:
        texto_limpo = texto_limpo[inicio:fim + 1]
    lista = json.loads(texto_limpo)
    return [normalizar_item_treino(item) for item in lista]

def saudacao_horario() -> str:
    hora = datetime.now(ZoneInfo("America/Sao_Paulo")).hour
    if 5 <= hora < 12:
        return "Bom dia"
    elif 12 <= hora < 18:
        return "Boa tarde"
    return "Boa noite"

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

def gerar_arquivo_ics(usuario: str, semana: int, planilha: list) -> str:
    hoje = datetime.now()
    dias_ate_segunda = (7 - hoje.weekday()) % 7
    base_segunda = hoje + timedelta(days=dias_ate_segunda)

    eventos = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Treinador Pessoal//PT-BR//EN",
        "CALSCALE:GREGORIAN"
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
        uid = f"treinador-{usuario}-s{semana}-{idx}-{int(hoje.timestamp())}@treinador"

        summary = f"[{item['modalidade']}] {item['titulo']} ({item['duracao_ou_dist']})"
        desc = item["descricao"].replace("\n", " ")

        eventos.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{hoje.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{dt_inicio}",
            f"DTEND:{dt_fim}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT"
        ])

    eventos.append("END:VCALENDAR")
    return "\r\n".join(eventos)

# ==========================================
# BARRA LATERAL (PERFIL E ROTINA)
# ==========================================
with st.sidebar:
    st.markdown("### 🏃 Seu Treinador")
    st.caption("Planejamento simples, adaptado à sua rotina.")
    st.divider()

    usuario_input = st.text_input(
        "Seu nome ou apelido",
        value=st.session_state.get("usuario_atual", ""),
        placeholder="Ex: joao"
    ).strip().lower()

    if not usuario_input:
        st.info("Digite seu nome acima para abrir seus treinos.")
        st.caption(f"Versão {VERSAO_APP}")
        st.stop()

    if st.session_state.get("usuario_atual") != usuario_input:
        st.session_state["usuario_atual"] = usuario_input
        st.session_state["dados_atleta"] = carregar_dados_usuario(usuario_input)

    dados_atleta = st.session_state["dados_atleta"]
    perfil = dados_atleta.get("perfil", {})
    provas_salvas = dados_atleta.get("provas", [])

    st.caption(f"Olá, **{usuario_input.capitalize()}** • Tudo salvo automaticamente")

    st.divider()
    st.markdown("**Dias que você pode treinar**")
    dias_salvos = perfil.get("dias_disponiveis", ["Segunda", "Quarta", "Sexta", "Sábado"])
    dias_selecionados = st.multiselect(
        "Selecione os dias:",
        options=DIAS_SEMANA_ORDEM,
        default=[d for d in dias_salvos if d in DIAS_SEMANA_ORDEM],
        label_visibility="collapsed"
    )
    dias_selecionados = [d for d in DIAS_SEMANA_ORDEM if d in dias_selecionados]

    if dias_selecionados != dias_salvos and perfil:
        dados_atleta["perfil"]["dias_disponiveis"] = dias_selecionados
        salvar_dados_usuario(usuario_input, dados_atleta)

    st.divider()
    with st.expander("Recomeçar do zero"):
        st.caption("Apaga sua planilha atual e o histórico para montar um plano novo.")
        if st.button("Apagar e recomeçar", use_container_width=True):
            st.session_state["dados_atleta"] = estrutura_padrao()
            salvar_dados_usuario(usuario_input, st.session_state["dados_atleta"])
            st.rerun()

    st.divider()
    st.caption(f"Versão {VERSAO_APP}")

# ==========================================
# CABEÇALHO HUMANO NO TOPO
# ==========================================
semana_num = dados_atleta.get("semana_atual", 1)
esporte_atual = perfil.get("esporte", "Treino Personalizado")
objetivo_atual = perfil.get("objetivo", "Evoluir com consistência")
proxima_prova = obter_proxima_prova(provas_salvas)

if proxima_prova:
    dias_f = proxima_prova["dias_restantes"]
    fase_nome, fase_desc = calcular_fase_periodizacao(dias_f)
    texto_dias = "É hoje! Boa prova!" if dias_f == 0 else (
        "Falta 1 dia para a prova" if dias_f == 1 else f"Faltam {dias_f} dias para {proxima_prova['nome']}"
    )
    subtitulo_topo = f"{texto_dias} ({proxima_prova['modalidade']}) • {fase_desc}"
    pill_html = f'<div class="pill-fase">Semana {semana_num} • {fase_nome} • {VERSAO_APP}</div>'
else:
    subtitulo_topo = f"{esporte_atual} • Foco: {objetivo_atual}"
    pill_html = f'<div class="pill-fase">Semana {semana_num} de treino • {VERSAO_APP}</div>'

st.markdown(f"""
<div class="welcome-card">
    <div class="welcome-title">{saudacao_horario()}, {usuario_input.capitalize()}! 👋</div>
    <div class="welcome-sub">{subtitulo_topo}</div>
    {pill_html}
</div>
""", unsafe_allow_html=True)

planilha_atual = dados_atleta.get("planilha", [])

# ==========================================
# TELA 1: SEM PLANILHA ATIVA
# ==========================================
if not planilha_atual:
    aba_criar, aba_importar = st.tabs(["✨ Montar meu plano", "📥 Já tenho uma planilha"])

    with aba_criar:
        col1, col2 = st.columns(2)
        with col1:
            esporte = st.selectbox(
                "O que você vai treinar?",
                ["Corrida de Rua", "Triathlon", "Musculação / Hipertrofia", "Ciclismo", "Natação", "CrossFit / Funcional", "Híbrido (Corrida + Musculação)"]
            )
            nivel = st.selectbox("Como está seu ritmo hoje?", ["Iniciante", "Intermediário", "Avançado"])
        with col2:
            objetivo = st.text_input("Qual é o seu objetivo?", placeholder="Ex: Completar meus primeiros 5 km / Triathlon SuperSprint")
            observacoes = st.text_area("Algo que eu precise saber sobre você?", placeholder="Ex: Tenho 45 min por dia, prefiro treinar de manhã...", height=100)

        st.markdown("**Vai fazer alguma prova em breve? (Opcional)**")
        c_p1, c_p2, c_p3 = st.columns([2, 1.5, 1.2])
        with c_p1:
            prova_init_nome = st.text_input("Nome da prova", placeholder="Ex: Corrida da Cidade 5km", key="p_init_nome")
        with c_p2:
            prova_init_mod = st.text_input("Distância / Modalidade", placeholder="Ex: 5 km ou SuperSprint", key="p_init_mod")
        with c_p3:
            prova_init_data = st.date_input("Data da prova", value=date.today() + timedelta(days=45), min_value=date.today(), key="p_init_data")

        if st.button("Montar minha primeira semana", type="primary", use_container_width=True):
            if not dias_selecionados:
                st.error("Escolha pelo menos 1 dia na barra lateral para treinar.")
            else:
                with st.spinner("Preparando seus treinos com carinho..."):
                    try:
                        provas_iniciais = []
                        if prova_init_nome.strip():
                            provas_iniciais.append({
                                "nome": prova_init_nome.strip(),
                                "modalidade": prova_init_mod.strip() or esporte,
                                "data": prova_init_data.isoformat()
                            })

                        dias_descanso = [d for d in DIAS_SEMANA_ORDEM if d not in dias_selecionados]
                        info_provas = resumo_provas_para_ia(provas_iniciais)

                        prompt = f"""
Você é um treinador humano, atencioso e experiente. Monte os treinos da Semana 1 para este aluno:
- Esporte principal: {esporte}
- Nível atual: {nivel}
- Objetivo: {objetivo or 'Evoluir com saúde e consistência'}
- Dias disponíveis para treinar: {', '.join(dias_selecionados)}
- Dias de descanso: {', '.join(dias_descanso) if dias_descanso else 'Nenhum'}
- Observações pessoais: {observacoes or 'Nenhuma'}
- Provas no calendário:
{info_provas}

REGRAS:
1. Retorne os 7 dias da semana na ordem: Segunda, Terça, Quarta, Quinta, Sexta, Sábado, Domingo.
2. Coloque treino APENAS nos dias disponíveis ({', '.join(dias_selecionados)}). Nos outros dias, use "modalidade": "Descanso" e "titulo": "Dia de descanso".
3. Escreva as descrições em linguagem humana, clara e encorajadora (aquecimento, treino principal e volta à calma), sem jargões robóticos.
4. Retorne EXCLUSIVAMENTE um array JSON válido (sem texto fora do JSON) com as chaves:
   "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist"
"""
                        resposta = gerar_resposta_ia(prompt)
                        nova_planilha = extrair_json_planilha(resposta)
                        dados_atleta["perfil"] = {
                            "esporte": esporte,
                            "nivel": nivel,
                            "objetivo": objetivo or "Evolução contínua",
                            "dias_disponiveis": dias_selecionados,
                            "observacoes": observacoes
                        }
                        dados_atleta["provas"] = provas_iniciais
                        dados_atleta["semana_atual"] = 1
                        dados_atleta["planilha"] = nova_planilha
                        salvar_dados_usuario(usuario_input, dados_atleta)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ops, tive um problema ao montar seu plano: {e}")

    with aba_importar:
        st.write("Cole o texto da planilha que você já segue para eu organizar por aqui:")
        texto_importado = st.text_area("Sua planilha atual:", height=180, placeholder="Segunda: Corrida leve 5km\nQuarta: Tiros 6x400m...")
        esporte_imp = st.text_input("Qual é o esporte principal?", value="Corrida")

        if st.button("Organizar minha planilha", type="primary", use_container_width=True):
            if not texto_importado.strip():
                st.error("Cole o texto da planilha primeiro.")
            else:
                with st.spinner("Organizando seus treinos..."):
                    try:
                        prompt = f"""
Organize a planilha abaixo nos 7 dias da semana (Segunda a Domingo).
Planilha:
{texto_importado}

Retorne EXCLUSIVAMENTE um array JSON válido com 7 objetos (Segunda a Domingo) e as chaves:
"dia", "modalidade", "titulo", "descricao", "duracao_ou_dist"
"""
                        resposta = gerar_resposta_ia(prompt)
                        nova_planilha = extrair_json_planilha(resposta)
                        dados_atleta["perfil"] = {
                            "esporte": esporte_imp,
                            "nivel": "Intermediário",
                            "objetivo": "Evolução contínua",
                            "dias_disponiveis": dias_selecionados
                        }
                        dados_atleta["semana_atual"] = 1
                        dados_atleta["planilha"] = nova_planilha
                        salvar_dados_usuario(usuario_input, dados_atleta)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Não consegui ler essa planilha: {e}")

# ==========================================
# TELA 2: PLANILHA ATIVA + PROVAS + HISTÓRICO
# ==========================================
else:
    treinos_ativos = [t for t in planilha_atual if t.get("modalidade", "").lower() != "descanso"]
    concluidos = [t for t in treinos_ativos if t.get("concluido")]
    progresso_ratio = (len(concluidos) / len(treinos_ativos)) if treinos_ativos else 0.0
    taxa_adesao = int(round(progresso_ratio * 100))

    # 3 Cartões minimalistas (sem RPE)
    m1, m2, m3 = st.columns(3)
    m1.metric("Treinos concluídos", f"{len(concluidos)} de {len(treinos_ativos)}")
    m2.metric("Consistência da semana", f"{taxa_adesao}%")
    if proxima_prova:
        dias_r = proxima_prova["dias_restantes"]
        m3.metric("Próxima prova", "Hoje!" if dias_r == 0 else f"Em {dias_r} dias", delta=proxima_prova["nome"], delta_color="off")
    else:
        m3.metric("Calendário de provas", "Nenhuma marcada", delta="Cadastre na aba Provas", delta_color="off")

    st.progress(progresso_ratio)
    st.write("")

    tab_treinos, tab_provas, tab_chat, tab_historico, tab_exportar = st.tabs([
        "🏃 Treinos da Semana",
        "🏆 Minhas Provas",
        "💬 Falar com Treinador",
        "📖 Semanas Anteriores",
        "📤 Enviar / Agenda"
    ])

    # ------------------------------------------
    # ABA 1: TREINOS DA SEMANA + GARMIN/STRAVA
    # ------------------------------------------
    with tab_treinos:
        st.caption("Marque o que você já fez, conte como se sentiu ou envie o arquivo do seu relógio (Garmin / Strava).")

        for i, item in enumerate(planilha_atual):
            eh_descanso = item.get("modalidade", "").lower() == "descanso"
            icone = "😴" if eh_descanso else ("✅" if item.get("concluido") else "🔸")
            titulo_card = f"{icone} {item['dia']} — {item['modalidade']}: {item['titulo']} ({item['duracao_ou_dist']})"

            with st.expander(titulo_card, expanded=not eh_descanso and not item.get("concluido")):
                st.markdown(item["descricao"])

                if item.get("dados_arquivo"):
                    st.success(f"⌚ Atividade importada: **{item['dados_arquivo']}**")

                if not eh_descanso:
                    st.divider()
                    c1, c2 = st.columns([1, 1.5])
                    with c1:
                        novo_status = st.checkbox(
                            "Já fiz esse treino",
                            value=item.get("concluido", False),
                            key=f"conc_{semana_num}_{i}"
                        )
                        if novo_status != item.get("concluido", False):
                            planilha_atual[i]["concluido"] = novo_status
                            dados_atleta["planilha"] = planilha_atual
                            salvar_dados_usuario(usuario_input, dados_atleta)
                            st.rerun()

                    with c2:
                        idx_sens = SENSAÇÕES_OPCOES.index(item.get("sensacao", "Ainda não fiz")) if item.get("sensacao") in SENSAÇÕES_OPCOES else 0
                        planilha_atual[i]["sensacao"] = st.selectbox(
                            "Como você se sentiu?",
                            options=SENSAÇÕES_OPCOES,
                            index=idx_sens,
                            key=f"sens_{semana_num}_{i}"
                        )

                    planilha_atual[i]["feedback"] = st.text_input(
                        "Anotações sobre o treino (opcional)",
                        value=item.get("feedback", ""),
                        placeholder="Ex: Consegui manter o ritmo no final, me senti bem...",
                        key=f"fb_{semana_num}_{i}"
                    )

                    arquivo_up = st.file_uploader(
                        "Enviar arquivo do Garmin ou Strava (.fit, .tcx, .gpx)",
                        type=["fit", "tcx", "gpx"],
                        key=f"up_{semana_num}_{i}"
                    )
                    if arquivo_up is not None:
                        try:
                            resumo_arq = processar_arquivo_atividade(arquivo_up)
                            if planilha_atual[i].get("dados_arquivo") != resumo_arq:
                                planilha_atual[i]["dados_arquivo"] = resumo_arq
                                planilha_atual[i]["concluido"] = True
                                if planilha_atual[i]["sensacao"] == "Ainda não fiz":
                                    planilha_atual[i]["sensacao"] = "Na medida certa"
                                dados_atleta["planilha"] = planilha_atual
                                salvar_dados_usuario(usuario_input, dados_atleta)
                                st.rerun()
                        except Exception as e:
                            st.error(f"Não consegui ler esse arquivo: {e}")

        st.write("")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("💾 Salvar anotações", use_container_width=True):
                dados_atleta["planilha"] = planilha_atual
                salvar_dados_usuario(usuario_input, dados_atleta)
                st.success("Tudo salvo!")

        with col_b2:
            if st.button("Fechar semana e montar a próxima ➡️", type="primary", use_container_width=True):
                if not dias_selecionados:
                    st.error("Escolha pelo menos 1 dia de treino na barra lateral.")
                else:
                    with st.spinner("Analisando sua semana e preparando a próxima..."):
                        try:
                            historico = dados_atleta.get("historico", [])
                            historico.append({
                                "semana": semana_num,
                                "data_fechamento": datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y"),
                                "adesao": taxa_adesao,
                                "treinos_concluidos": len(concluidos),
                                "treinos_totais": len(treinos_ativos),
                                "planilha": json.loads(json.dumps(planilha_atual))
                            })

                            dias_descanso = [d for d in DIAS_SEMANA_ORDEM if d not in dias_selecionados]
                            info_provas = resumo_provas_para_ia(provas_salvas)
                            resumo_semana = json.dumps(planilha_atual, ensure_ascii=False)

                            prompt = f"""
Você é um treinador humano, próximo e atento. Analise como foi a Semana {semana_num} deste aluno e monte os treinos da Semana {semana_num + 1}.

Perfil do aluno: {json.dumps(dados_atleta.get('perfil', {}), ensure_ascii=False)}
Calendário de provas alvo (ajuste a periodização, volume e intensidade pensando nestas datas):
{info_provas}

Dias disponíveis para treinar na Semana {semana_num + 1}: {', '.join(dias_selecionados)}
Dias de descanso: {', '.join(dias_descanso) if dias_descanso else 'Nenhum'}

Como foi a Semana {semana_num} (inclui sensações, anotações e dados reais importados do Garmin/Strava em 'dados_arquivo'):
{resumo_semana}

COMO PLANEJAR A PRÓXIMA SEMANA:
- Respeite a fase da prova (Base, Construção, Pico ou Polimento na semana da prova).
- Se o aluno completou bem e se sentiu leve/na medida, evolua gradualmente.
- Se relatou cansaço, treino pesado/exausto ou faltou a treinos, segure um pouco a carga para ele recuperar bem.
- Coloque treinos APENAS nos dias selecionados ({', '.join(dias_selecionados)}). Nos outros dias, coloque "modalidade": "Descanso".
- Retorne EXCLUSIVAMENTE um array JSON válido com os 7 dias (Segunda a Domingo) e as chaves: "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist".
"""
                            resposta = gerar_resposta_ia(prompt)
                            proxima_planilha = extrair_json_planilha(resposta)

                            dados_atleta["historico"] = historico
                            dados_atleta["semana_atual"] = semana_num + 1
                            dados_atleta["planilha"] = proxima_planilha
                            salvar_dados_usuario(usuario_input, dados_atleta)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Não consegui gerar a próxima semana agora: {e}")

    # ------------------------------------------
    # ABA 2: CALENDÁRIO DE PROVAS
    # ------------------------------------------
    with tab_provas:
        st.subheader("🏆 Suas Provas Alvo")
        st.write("Cadastre as provas que você pretende fazer. Eu organizo seus treinos automaticamente para você chegar preparado no dia.")

        with st.form("form_nova_prova", clear_on_submit=True):
            cp1, cp2, cp3 = st.columns([2, 1.5, 1.2])
            with cp1:
                nova_prova_nome = st.text_input("Nome da prova", placeholder="Ex: Meia Maratona de Vitória")
            with cp2:
                nova_prova_mod = st.text_input("Modalidade / Distância", placeholder="Ex: Corrida 21 km / Triathlon")
            with cp3:
                nova_prova_data = st.date_input("Data", value=date.today() + timedelta(days=30), min_value=date.today())

            if st.form_submit_button("Adicionar ao calendário", type="primary"):
                if not nova_prova_nome.strip():
                    st.warning("Coloque o nome da prova antes de salvar.")
                else:
                    provas_salvas.append({
                        "nome": nova_prova_nome.strip(),
                        "modalidade": nova_prova_mod.strip() or esporte_atual,
                        "data": nova_prova_data.isoformat()
                    })
                    dados_atleta["provas"] = provas_salvas
                    salvar_dados_usuario(usuario_input, dados_atleta)
                    st.success("Prova adicionada! Seus próximos treinos já vão considerar essa data.")
                    st.rerun()

        st.divider()
        if provas_salvas:
            hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
            provas_ordenadas = sorted(provas_salvas, key=lambda x: x.get("data", ""))

            for idx_p, p in enumerate(provas_ordenadas):
                try:
                    dt_p = date.fromisoformat(p["data"])
                    dias_rest = (dt_p - hoje).days
                    data_fmt = dt_p.strftime("%d/%m/%Y")
                except Exception:
                    dias_rest = -1
                    data_fmt = p.get("data", "")

                col_info, col_del = st.columns([4, 1])
                with col_info:
                    if dias_rest >= 0:
                        fase_p, desc_p = calcular_fase_periodizacao(dias_rest)
                        contagem = "É hoje!" if dias_rest == 0 else f"Faltam {dias_rest} dias"
                        st.markdown(
                            f"**{p['nome']}** ({p['modalidade']}) — 📅 {data_fmt}  \n"
                            f"⏳ **{contagem}** • *{fase_p}:* {desc_p}"
                        )
                    else:
                        st.markdown(f"**{p['nome']}** ({p['modalidade']}) — 📅 {data_fmt} *(Prova já realizada)*")

                with col_del:
                    if st.button("Remover", key=f"del_prova_{idx_p}", use_container_width=True):
                        provas_salvas.remove(p)
                        dados_atleta["provas"] = provas_salvas
                        salvar_dados_usuario(usuario_input, dados_atleta)
                        st.rerun()
                st.write("")
        else:
            st.info("Você ainda não marcou nenhuma prova. Cadastre uma acima para ativar a preparação específica!")

    # ------------------------------------------
    # ABA 3: CONVERSAR COM O TREINADOR
    # ------------------------------------------
    with tab_chat:
        st.subheader("💬 Precisa adaptar algum treino?")
        st.write("Mudou seu horário, choveu ou bateu um cansaço extra? Me conta o que houve que eu reorganizo a semana para você.")

        pedido_ajuste = st.text_area(
            "O que você gostaria de mudar?",
            placeholder="Ex: Hoje não deu tempo de correr, joga esse treino para amanhã.\nEx: Senti a panturrilha pesada, deixa o próximo treino bem leve.",
            height=110
        )

        if st.button("Adaptar meus treinos", type="primary"):
            if not pedido_ajuste.strip():
                st.warning("Me diga o que você precisa mudar primeiro.")
            else:
                with st.spinner("Reorganizando sua semana..."):
                    try:
                        prompt_ajuste = f"""
Você é um treinador humano e flexível. O aluno pediu uma adaptação na Semana {semana_num}.

Treinos atuais em JSON:
{json.dumps(planilha_atual, ensure_ascii=False)}

Provas cadastradas:
{resumo_provas_para_ia(provas_salvas)}

Pedido do aluno:
"{pedido_ajuste}"

REGRAS:
1. Ajuste APENAS os dias necessários para atender o aluno, mantendo intactos os treinos já feitos ("concluido", "sensacao", "feedback", "dados_arquivo").
2. Mantenha os 7 dias da semana (Segunda a Domingo).
3. Retorne EXCLUSIVAMENTE o array JSON atualizado com as chaves: "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist", "concluido", "sensacao", "feedback", "dados_arquivo".
"""
                        resposta = gerar_resposta_ia(prompt_ajuste)
                        planilha_ajustada = extrair_json_planilha(resposta)
                        dados_atleta["planilha"] = planilha_ajustada
                        salvar_dados_usuario(usuario_input, dados_atleta)
                        st.success("Pronto! Já atualizei seus treinos.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Não consegui fazer o ajuste agora: {e}")

    # ------------------------------------------
    # ABA 4: HISTÓRICO MINIMALISTA
    # ------------------------------------------
    with tab_historico:
        st.subheader("📖 Semanas Anteriores")
        historico = dados_atleta.get("historico", [])

        if historico:
            opcoes_semanas = [
                f"Semana {h['semana']} ({h.get('data_fechamento', '')}) • {h.get('treinos_concluidos', 0)}/{h.get('treinos_totais', 0)} treinos ({h.get('adesao', 0)}%)"
                for h in reversed(historico)
            ]
            escolha = st.selectbox("Escolha uma semana para rever:", opcoes_semanas)
            idx_escolhido = len(historico) - 1 - opcoes_semanas.index(escolha)
            registro_semana = historico[idx_escolhido]

            planilha_arquivada = registro_semana.get("planilha", [])
            if planilha_arquivada:
                for t_ant in planilha_arquivada:
                    if t_ant.get("modalidade", "").lower() == "descanso":
                        st.markdown(f"😴 **{t_ant['dia']}:** Descanso")
                    else:
                        status_txt = "✅ Feito" if t_ant.get("concluido") else "⬜ Não feito"
                        sens_txt = f" • Sensação: {t_ant['sensacao']}" if t_ant.get("sensacao") and t_ant.get("sensacao") != "Ainda não fiz" else ""
                        arq_txt = f" • ⌚ {t_ant['dados_arquivo']}" if t_ant.get("dados_arquivo") else ""
                        fb_txt = f"\n\n*\"{t_ant['feedback']}\"* " if t_ant.get("feedback") else ""

                        st.markdown(
                            f"**{t_ant['dia']} — {t_ant['modalidade']}: {t_ant['titulo']}** ({t_ant['duracao_ou_dist']})  \n"
                            f"{status_txt}{sens_txt}{arq_txt}{fb_txt}"
                        )
                        st.divider()
            else:
                st.caption("Resumo numérico salvo desta semana.")
        else:
            st.info("Quando você concluir esta semana e gerar a próxima, o resumo dela vai aparecer aqui.")

    # ------------------------------------------
    # ABA 5: EXPORTAR (WHATSAPP & AGENDA)
    # ------------------------------------------
    with tab_exportar:
        st.subheader("📤 Levar treinos para o celular")
        col_ex1, col_ex2 = st.columns(2)

        with col_ex1:
            st.markdown("**Copiar para o WhatsApp**")
            texto_wpp = gerar_texto_whatsapp(usuario_input, semana_num, planilha_atual)
            st.text_area("Texto formatado:", value=texto_wpp, height=240)

        with col_ex2:
            st.markdown("**Adicionar ao Calendário (Google / Apple)**")
            st.write("Baixe o arquivo abaixo para colocar os treinos da semana na sua agenda.")
            ics_conteudo = gerar_arquivo_ics(usuario_input, semana_num, planilha_atual)
            st.download_button(
                label="📅 Baixar para minha Agenda (.ics)",
                data=ics_conteudo,
                file_name=f"treinos_semana_{semana_num}_{usuario_input}.ics",
                mime="text/calendar",
                type="primary",
                use_container_width=True
            )
