import streamlit as st
import pandas as pd
import json
import re
from datetime import datetime, timedelta
from google import genai
from supabase import create_client, Client

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Coach IA • Performance & Treinos",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# CSS CUSTOMIZADO (DESIGN DARK PERFORMANCE)
# ==========================================
st.markdown("""
<style>
    /* Esconde elementos padrão do Streamlit para visual de App nativo */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background: transparent !important;}

    /* Fundo e tipografia geral */
    .stApp {
        background: radial-gradient(circle at top right, #162038 0%, #0B0F19 45%);
    }

    /* Banner Hero no topo */
    .hero-banner {
        background: linear-gradient(135deg, #161F33 0%, #1E293B 100%);
        border: 1px solid rgba(255, 90, 31, 0.35);
        border-left: 6px solid #FF5A1F;
        border-radius: 14px;
        padding: 22px 26px;
        margin-bottom: 22px;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.35);
    }
    .hero-title {
        font-size: 1.85rem;
        font-weight: 800;
        color: #FFFFFF;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .hero-sub {
        font-size: 0.95rem;
        color: #94A3B8;
        margin-top: 6px;
    }
    .badge-orange {
        background-color: rgba(255, 90, 31, 0.18);
        color: #FF7A45;
        border: 1px solid rgba(255, 90, 31, 0.4);
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
        margin-left: 8px;
    }

    /* Cartões de Métricas (KPIs) */
    div[data-testid="stMetric"] {
        background-color: #131A2A;
        border: 1px solid #232F46;
        border-radius: 12px;
        padding: 14px 18px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
    div[data-testid="stMetric"] label {
        color: #94A3B8 !important;
        font-size: 0.85rem !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #F8FAFC !important;
        font-weight: 800 !important;
    }

    /* Expanders dos treinos */
    div[data-testid="stExpander"] {
        background-color: #131A2A !important;
        border: 1px solid #232F46 !important;
        border-radius: 12px !important;
        margin-bottom: 10px !important;
        transition: border-color 0.2s ease;
    }
    div[data-testid="stExpander"]:hover {
        border-color: #FF5A1F !important;
    }

    /* Abas estilizadas */
    button[data-baseweb="tab"] {
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        padding: 10px 18px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #FF5A1F !important;
    }

    /* Botões principais */
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #FF5A1F 0%, #FF7847 100%) !important;
        border: none !important;
        color: white !important;
        font-weight: 700 !important;
        border-radius: 10px !important;
        padding: 0.6rem 1.2rem !important;
        box-shadow: 0 4px 14px rgba(255, 90, 31, 0.35) !important;
    }
    .stButton > button[kind="secondary"] {
        border-radius: 10px !important;
        border: 1px solid #2D3B55 !important;
        background-color: #161F33 !important;
    }
</style>
""", unsafe_allow_html=True)

DIAS_SEMANA_ORDEM = [
    "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"
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
        raise ValueError("Chave GEMINI_API_KEY não encontrada nos Secrets.")

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
# PERSISTÊNCIA NA NUVEM (SUPABASE)
# ==========================================
def estrutura_padrao():
    return {
        "perfil": {},
        "semana_atual": 1,
        "planilha": [],
        "historico": []
    }

def normalizar_item_treino(item: dict) -> dict:
    return {
        "dia": str(item.get("dia", "Dia")),
        "modalidade": str(item.get("modalidade") or item.get("esporte") or item.get("tipo") or "Treino"),
        "titulo": str(item.get("titulo") or item.get("treino") or item.get("foco") or "Sessão"),
        "descricao": str(item.get("descricao") or item.get("detalhes") or item.get("prescricao") or ""),
        "duracao_ou_dist": str(item.get("duracao_ou_dist") or item.get("volume") or item.get("duracao") or "-"),
        "rpe_alvo": int(item.get("rpe_alvo", 5) or 5),
        "concluido": bool(item.get("concluido", False)),
        "rpe_real": int(item.get("rpe_real", 0) or 0),
        "feedback": str(item.get("feedback", ""))
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
            return base
    except Exception as e:
        st.error(f"Erro ao carregar dados do Supabase: {e}")
    return estrutura_padrao()

def salvar_dados_usuario(usuario: str, dados: dict):
    sb = get_supabase_client()
    if not sb:
        st.warning("Supabase não configurado. Os dados ficarão apenas nesta sessão.")
        return
    try:
        sb.table("atletas").upsert({
            "usuario": usuario,
            "dados": dados
        }).execute()
    except Exception as e:
        st.error(f"Erro ao salvar no Supabase: {e}")

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
    planilha_normalizada = []
    for item in lista:
        planilha_normalizada.append({
            "dia": str(item.get("dia", "")),
            "modalidade": str(item.get("modalidade", "Descanso")),
            "titulo": str(item.get("titulo", "Descanso")),
            "descricao": str(item.get("descricao", "")),
            "duracao_ou_dist": str(item.get("duracao_ou_dist", "-")),
            "rpe_alvo": int(item.get("rpe_alvo", 0) or 0),
            "concluido": bool(item.get("concluido", False)),
            "rpe_real": int(item.get("rpe_real", 0) or 0),
            "feedback": str(item.get("feedback", ""))
        })
    return planilha_normalizada

def gerar_texto_whatsapp(usuario: str, semana: int, planilha: list) -> str:
    linhas = [f"⚡ *PLANILHA DE TREINOS - SEMANA {semana}* ({usuario.upper()})", ""]
    for item in planilha:
        status = "✅" if item.get("concluido") else "⬜"
        if item.get("modalidade", "").lower() == "descanso":
            linhas.append(f"😴 *{item['dia']}:* Descanso")
        else:
            rpe_txt = f" | RPE Alvo: {item['rpe_alvo']}/10" if item.get("rpe_alvo") else ""
            linhas.append(
                f"{status} *{item['dia']} — {item['modalidade']} ({item['titulo']})*\n"
                f"   📏 {item['duracao_ou_dist']}{rpe_txt}\n"
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
        "PRODID:-//Coach IA Treinos//PT-BR//EN",
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
        uid = f"coachia-{usuario}-s{semana}-{idx}-{int(hoje.timestamp())}@treinadoria"

        summary = f"[{item['modalidade']}] {item['titulo']} ({item['duracao_ou_dist']})"
        desc = f"{item['descricao']} | RPE Alvo: {item['rpe_alvo']}/10".replace("\n", " ")

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
# BARRA LATERAL (PERFIL E DIAS DE TREINO)
# ==========================================
with st.sidebar:
    st.markdown("## ⚡ COACH **IA**")
    st.caption("Plataforma de Treinamento Adaptativo")
    st.divider()

    usuario_input = st.text_input(
        "👤 Identificação do Atleta",
        value=st.session_state.get("usuario_atual", ""),
        placeholder="Digite seu nome ou apelido..."
    ).strip().lower()

    if not usuario_input:
        st.info("Digite seu nome acima para carregar ou criar sua planilha na nuvem.")
        st.stop()

    if st.session_state.get("usuario_atual") != usuario_input:
        st.session_state["usuario_atual"] = usuario_input
        st.session_state["dados_atleta"] = carregar_dados_usuario(usuario_input)

    dados_atleta = st.session_state["dados_atleta"]
    perfil = dados_atleta.get("perfil", {})

    st.success(f"Conectado: **{usuario_input.capitalize()}**")

    st.divider()
    st.markdown("### 📅 Dias Disponíveis")
    dias_salvos = perfil.get("dias_disponiveis", ["Segunda", "Quarta", "Sexta", "Sábado"])
    dias_selecionados = st.multiselect(
        "Escolha os dias de treino (Seg a Dom):",
        options=DIAS_SEMANA_ORDEM,
        default=[d for d in dias_salvos if d in DIAS_SEMANA_ORDEM],
        help="Os dias não selecionados serão configurados automaticamente como Descanso."
    )
    dias_selecionados = [d for d in DIAS_SEMANA_ORDEM if d in dias_selecionados]

    if dias_selecionados != dias_salvos and perfil:
        dados_atleta["perfil"]["dias_disponiveis"] = dias_selecionados
        salvar_dados_usuario(usuario_input, dados_atleta)

    st.divider()
    with st.expander("⚙️ Zona de Perigo"):
        st.caption("Apaga sua planilha atual e histórico para começar do zero.")
        if st.button("🗑️ Resetar Meus Treinos", use_container_width=True):
            st.session_state["dados_atleta"] = estrutura_padrao()
            salvar_dados_usuario(usuario_input, st.session_state["dados_atleta"])
            st.rerun()

# ==========================================
# BANNER HERO NO TOPO
# ==========================================
semana_num = dados_atleta.get("semana_atual", 1)
esporte_atual = perfil.get("esporte", "Treinamento Personalizado")
objetivo_atual = perfil.get("objetivo", "Evolução contínua e performance")

st.markdown(f"""
<div class="hero-banner">
    <div class="hero-title">
        ⚡ Painel de Performance • {usuario_input.capitalize()}
        <span class="badge-orange">SEMANA {semana_num}</span>
    </div>
    <div class="hero-sub">
        🏅 <strong>Modalidade:</strong> {esporte_atual} &nbsp;|&nbsp; 🎯 <strong>Foco:</strong> {objetivo_atual}
    </div>
</div>
""", unsafe_allow_html=True)

planilha_atual = dados_atleta.get("planilha", [])

# ==========================================
# TELA 1: SEM PLANILHA ATIVA (CRIAR OU IMPORTAR)
# ==========================================
if not planilha_atual:
    aba_criar, aba_importar = st.tabs(["✨ Criar Planilha do Zero", "📥 Importar Planilha Existente"])

    with aba_criar:
        col1, col2 = st.columns(2)
        with col1:
            esporte = st.selectbox(
                "Modalidade Principal:",
                ["Corrida de Rua", "Musculação / Hipertrofia", "Triathlon", "Ciclismo", "CrossFit / Funcional", "Natação", "Híbrido (Corrida + Musculação)"]
            )
            nivel = st.selectbox("Nível Atual:", ["Iniciante", "Intermediário", "Avançado"])
        with col2:
            objetivo = st.text_input("Objetivo Principal:", placeholder="Ex: Correr 10km abaixo de 50min / Ganhar massa muscular")
            observacoes = st.text_area("Observações / Limitações:", placeholder="Ex: Tenho 45 min por dia, sem lesões...")

        if st.button("🚀 Gerar Minha Planilha Inicial", type="primary", use_container_width=True):
            if not dias_selecionados:
                st.error("Selecione pelo menos 1 dia da semana na barra lateral para treinar!")
            else:
                with st.spinner("🤖 A IA está montando sua planilha personalizada..."):
                    try:
                        dias_descanso = [d for d in DIAS_SEMANA_ORDEM if d not in dias_selecionados]
                        prompt = f"""
Você é um treinador esportivo de elite. Crie uma planilha de treinos para a Semana 1 para o atleta abaixo:
- Modalidade: {esporte}
- Nível: {nivel}
- Objetivo: {objetivo or 'Condicionamento geral e evolução progressiva'}
- Dias disponíveis para treinar: {', '.join(dias_selecionados)}
- Dias de descanso obrigatório: {', '.join(dias_descanso) if dias_descanso else 'Nenhum'}
- Observações: {observacoes or 'Nenhuma'}

REGRAS OBRIGATÓRIAS:
1. Retorne os 7 dias da semana na ordem exata: Segunda, Terça, Quarta, Quinta, Sexta, Sábado, Domingo.
2. Coloque treinos APENAS nos dias disponíveis ({', '.join(dias_selecionados)}). Nos demais dias, coloque "modalidade": "Descanso" e "titulo": "Descanso / Recuperação".
3. Retorne EXCLUSIVAMENTE um array JSON válido (sem markdown, sem explicações fora do JSON), onde cada objeto tem exatamente estas chaves:
   - "dia": string ("Segunda", "Terça", etc.)
   - "modalidade": string (ex: "{esporte}" ou "Descanso")
   - "titulo": string (ex: "Treino Intervalado", "Rodagem Leve", "Descanso")
   - "descricao": string (detalhes claros do treino: aquecimento, parte principal, séries/ritmo, volta à calma)
   - "duracao_ou_dist": string (ex: "45 min" ou "6 km" ou "-")
   - "rpe_alvo": número inteiro de 1 a 10 (0 para descanso)
"""
                        resposta = gerar_resposta_ia(prompt)
                        nova_planilha = extrair_json_planilha(resposta)
                        dados_atleta["perfil"] = {
                            "esporte": esporte,
                            "nivel": nivel,
                            "objetivo": objetivo or "Evolução progressiva",
                            "dias_disponiveis": dias_selecionados,
                            "observacoes": observacoes
                        }
                        dados_atleta["semana_atual"] = 1
                        dados_atleta["planilha"] = nova_planilha
                        salvar_dados_usuario(usuario_input, dados_atleta)
                        st.success("Planilha criada e salva na nuvem!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao processar planilha: {e}")

    with aba_importar:
        st.write("Cole abaixo o texto ou tabela da sua planilha atual para que o Coach IA estruture e evolua a partir dela:")
        texto_importado = st.text_area("Cole sua planilha aqui:", height=190, placeholder="Ex:\nSegunda: Corrida leve 5km\nQuarta: Tiros 6x400m\nSexta: Musculação pernas...")
        esporte_imp = st.text_input("Modalidade principal dessa planilha:", value="Corrida / Treino Geral")

        if st.button("📥 Importar e Organizar Planilha", type="primary", use_container_width=True):
            if not texto_importado.strip():
                st.error("Cole o conteúdo da planilha antes de importar.")
            else:
                with st.spinner("🤖 Lendo e estruturando sua planilha..."):
                    try:
                        prompt = f"""
Converta e estruture a planilha de treino enviada abaixo para os 7 dias da semana (Segunda a Domingo).
Planilha enviada:
{texto_importado}

Retorne EXCLUSIVAMENTE um array JSON válido (sem texto extra), com 7 objetos (Segunda a Domingo), contendo:
- "dia": string ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")
- "modalidade": string (ex: "{esporte_imp}" ou "Descanso")
- "titulo": string
- "descricao": string
- "duracao_ou_dist": string
- "rpe_alvo": inteiro de 1 a 10 (0 para descanso)
"""
                        resposta = gerar_resposta_ia(prompt)
                        nova_planilha = extrair_json_planilha(resposta)
                        dados_atleta["perfil"] = {
                            "esporte": esporte_imp,
                            "nivel": "Base Importada",
                            "objetivo": "Evolução contínua",
                            "dias_disponiveis": dias_selecionados
                        }
                        dados_atleta["semana_atual"] = 1
                        dados_atleta["planilha"] = nova_planilha
                        salvar_dados_usuario(usuario_input, dados_atleta)
                        st.success("Planilha importada e salva na nuvem!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao importar planilha: {e}")

# ==========================================
# TELA 2: PLANILHA ATIVA + GRÁFICOS + HISTÓRICO + CHAT + EXPORTAÇÃO
# ==========================================
else:
    treinos_ativos = [t for t in planilha_atual if t.get("modalidade", "").lower() != "descanso"]
    concluidos = [t for t in treinos_ativos if t.get("concluido")]
    taxa_adesao = int((len(concluidos) / len(treinos_ativos) * 100)) if treinos_ativos else 0
    rpes_reais = [t.get("rpe_real", 0) for t in concluidos if t.get("rpe_real", 0) > 0]
    rpe_medio = round(sum(rpes_reais) / len(rpes_reais), 1) if rpes_reais else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ciclo Atual", f"Semana {semana_num}")
    m2.metric("Treinos Feitos", f"{len(concluidos)} de {len(treinos_ativos)}")
    m3.metric("Taxa de Adesão", f"{taxa_adesao}%")
    m4.metric("Esforço Médio (RPE)", f"{rpe_medio} / 10")

    st.write("")

    tab_planilha, tab_graficos, tab_chat, tab_exportar = st.tabs([
        "📋 Treinos da Semana",
        "📊 Gráficos & Histórico Completo",
        "💬 Chat com Treinador",
        "📅 WhatsApp & Agenda (.ics)"
    ])

    # ------------------------------------------
    # ABA 1: PLANILHA E REGISTRO DIÁRIO
    # ------------------------------------------
    with tab_planilha:
        st.caption("Marque os treinos concluídos, registre o esforço sentido (RPE 1 a 10) e salve seu progresso.")

        for i, item in enumerate(planilha_atual):
            eh_descanso = item.get("modalidade", "").lower() == "descanso"
            icone = "😴" if eh_descanso else ("✅" if item.get("concluido") else "🔥")
            badge_rpe = "" if eh_descanso else f" • RPE Alvo: {item.get('rpe_alvo', 5)}/10"
            titulo_expander = f"{icone} {item['dia'].upper()}  |  {item['modalidade']}: {item['titulo']} ({item['duracao_ou_dist']}){badge_rpe}"

            with st.expander(titulo_expander, expanded=not eh_descanso):
                st.markdown(f"**📋 Prescrição:** {item['descricao']}")
                if not eh_descanso:
                    st.divider()
                    c1, c2, c3 = st.columns([1, 1.2, 2.2])
                    with c1:
                        planilha_atual[i]["concluido"] = st.checkbox(
                            "Treino Concluído",
                            value=item.get("concluido", False),
                            key=f"conc_{semana_num}_{i}"
                        )
                    with c2:
                        val_rpe = item.get("rpe_real", 0) or item.get("rpe_alvo", 5) or 5
                        planilha_atual[i]["rpe_real"] = st.slider(
                            "RPE Real (1 a 10)",
                            min_value=1,
                            max_value=10,
                            value=int(val_rpe),
                            key=f"rpe_{semana_num}_{i}"
                        )
                    with c3:
                        planilha_atual[i]["feedback"] = st.text_input(
                            "Feedback / Sensações",
                            value=item.get("feedback", ""),
                            placeholder="Ex: Ritmo encaixou bem, pernas leves...",
                            key=f"fb_{semana_num}_{i}"
                        )

        st.write("")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("💾 Salvar Registro", use_container_width=True):
                dados_atleta["planilha"] = planilha_atual
                salvar_dados_usuario(usuario_input, dados_atleta)
                st.success("Progresso salvo na nuvem!")
                st.rerun()

        with col_btn2:
            if st.button("🔄 Finalizar Semana e Gerar Próxima", type="primary", use_container_width=True):
                if not dias_selecionados:
                    st.error("Selecione pelo menos 1 dia de treino na barra lateral.")
                else:
                    with st.spinner("🤖 Analisando seu desempenho e gerando a próxima semana..."):
                        try:
                            historico = dados_atleta.get("historico", [])
                            # Arquiva a semana completa (métricas + planilha inteira)
                            historico.append({
                                "semana": semana_num,
                                "data_fechamento": datetime.now().strftime("%d/%m/%Y"),
                                "adesao": taxa_adesao,
                                "rpe_medio": rpe_medio,
                                "treinos_concluidos": len(concluidos),
                                "treinos_totais": len(treinos_ativos),
                                "planilha": json.loads(json.dumps(planilha_atual))
                            })

                            dias_descanso = [d for d in DIAS_SEMANA_ORDEM if d not in dias_selecionados]
                            resumo_execucao = json.dumps(planilha_atual, ensure_ascii=False)

                            prompt = f"""
Você é um treinador esportivo de elite. Analise o desempenho da Semana {semana_num} deste atleta e gere a planilha evoluída para a Semana {semana_num + 1}.

Perfil do atleta: {json.dumps(dados_atleta.get('perfil', {}), ensure_ascii=False)}
Dias selecionados para treinar nesta nova semana: {', '.join(dias_selecionados)}
Dias de descanso obrigatório: {', '.join(dias_descanso) if dias_descanso else 'Nenhum'}

Desempenho registrado na Semana {semana_num}:
{resumo_execucao}

REGRAS DE EVOLUÇÃO:
- Se o atleta concluiu bem os treinos com RPE dentro ou abaixo do alvo, aplique sobrecarga progressiva segura (5% a 10% no volume ou intensidade).
- Se o atleta relatou fadiga excessiva, RPE muito acima do alvo ou pulou treinos, ajuste a carga para evitar lesão/overtraining.
- Coloque treinos APENAS nos dias selecionados ({', '.join(dias_selecionados)}). Nos outros dias, coloque "modalidade": "Descanso".
- Retorne EXCLUSIVAMENTE um array JSON válido com os 7 dias (Segunda a Domingo) e as chaves: "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist", "rpe_alvo".
"""
                            resposta = gerar_resposta_ia(prompt)
                            proxima_planilha = extrair_json_planilha(resposta)

                            dados_atleta["historico"] = historico
                            dados_atleta["semana_atual"] = semana_num + 1
                            dados_atleta["planilha"] = proxima_planilha
                            salvar_dados_usuario(usuario_input, dados_atleta)
                            st.success(f"Semana {semana_num + 1} gerada com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao gerar evolução: {e}")

    # ------------------------------------------
    # ABA 2: GRÁFICOS & HISTÓRICO COMPLETO
    # ------------------------------------------
    with tab_graficos:
        st.subheader(f"📊 Telemetria — Semana {semana_num}")

        df_semana = pd.DataFrame([
            {
                "Dia": t["dia"],
                "RPE Planejado": t.get("rpe_alvo", 0),
                "RPE Realizado": t.get("rpe_real", 0) if t.get("concluido") else 0,
                "Status": "Concluído" if t.get("concluido") else ("Descanso" if t.get("modalidade", "").lower() == "descanso" else "Pendente")
            }
            for t in planilha_atual
        ])

        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Esforço por Dia (RPE Planejado vs. Realizado)**")
            df_rpe = df_semana.set_index("Dia")[["RPE Planejado", "RPE Realizado"]]
            st.bar_chart(df_rpe, color=["#64748B", "#FF5A1F"])

        with g2:
            st.markdown("**Distribuição dos Treinos na Semana**")
            contagem_status = df_semana["Status"].value_counts()
            st.bar_chart(contagem_status, color="#10B981")

        st.divider()
        st.subheader("📖 Histórico Completo das Semanas Anteriores")
        historico = dados_atleta.get("historico", [])

        if historico:
            df_hist = pd.DataFrame(historico)
            df_hist["Semana"] = df_hist["semana"].apply(lambda x: f"Sem {x}")

            c_h1, c_h2 = st.columns(2)
            with c_h1:
                st.markdown("**Evolução da Taxa de Adesão (%)**")
                st.line_chart(df_hist.set_index("Semana")["adesao"], color="#10B981")
            with c_h2:
                st.markdown("**Evolução do Esforço Médio (RPE)**")
                st.line_chart(df_hist.set_index("Semana")["rpe_medio"], color="#FF5A1F")

            st.write("")
            st.markdown("#### 🔍 Consultar Planilha de uma Semana Passada")
            opcoes_semanas = [
                f"Semana {h['semana']} ({h.get('data_fechamento', 'Concluída')}) — Adesão: {h.get('adesao', 0)}% | RPE Médio: {h.get('rpe_medio', 0)}"
                for h in reversed(historico)
            ]
            escolha = st.selectbox("Selecione a semana que deseja rever:", opcoes_semanas)
            idx_escolhido = len(historico) - 1 - opcoes_semanas.index(escolha)
            registro_semana = historico[idx_escolhido]

            planilha_arquivada = registro_semana.get("planilha", [])
            if planilha_arquivada:
                for treino_ant in planilha_arquivada:
                    if treino_ant.get("modalidade", "").lower() == "descanso":
                        st.markdown(f"😴 **{treino_ant['dia']}:** Descanso")
                    else:
                        status_txt = "✅ Concluído" if treino_ant.get("concluido") else "❌ Não realizado"
                        rpe_txt = f" | RPE Real: **{treino_ant.get('rpe_real', '-')}/10**" if treino_ant.get("concluido") else ""
                        fb_txt = f" — *\"{treino_ant['feedback']}\"* " if treino_ant.get("feedback") else ""
                        st.info(
                            f"**{treino_ant['dia']} — {treino_ant['modalidade']}: {treino_ant['titulo']}** ({treino_ant['duracao_ou_dist']})\n\n"
                            f"{treino_ant['descricao']}\n\n"
                            f"{status_txt}{rpe_txt}{fb_txt}"
                        )
            else:
                st.caption("Esta semana antiga foi salva apenas com o resumo numérico.")
        else:
            st.info("Assim que você finalizar sua primeira semana clicando em **Finalizar Semana e Gerar Próxima**, todo o histórico detalhado ficará arquivado aqui!")

    # ------------------------------------------
    # ABA 3: CHAT RÁPIDO COM O TREINADOR
    # ------------------------------------------
    with tab_chat:
        st.subheader("💬 Ajustar Treino em Tempo Real")
        st.write("Choveu, bateu o cansaço ou mudou sua rotina? Peça a adaptação aqui e o Coach IA recalcula apenas o necessário:")

        pedido_ajuste = st.text_area(
            "Descreva o ajuste desejado:",
            placeholder="Ex: Hoje choveu muito, troca o treino de Quarta por um treino indoor de 30 minutos.\nEx: Senti um desconforto muscular, deixa o treino de Sexta regenerativo.",
            height=110
        )

        if st.button("🛠️ Aplicar Ajuste na Planilha", type="primary"):
            if not pedido_ajuste.strip():
                st.warning("Escreva qual ajuste você deseja fazer antes de enviar.")
            else:
                with st.spinner("🤖 O Treinador IA está recalculando sua planilha..."):
                    try:
                        prompt_ajuste = f"""
Você é um treinador esportivo. O atleta pediu um ajuste pontual na planilha atual da Semana {semana_num}.

Planilha atual em JSON:
{json.dumps(planilha_atual, ensure_ascii=False)}

Pedido do atleta:
"{pedido_ajuste}"

REGRAS:
1. Modifique APENAS os dias afetados pelo pedido do atleta, mantendo os outros dias e o progresso ("concluido", "rpe_real", "feedback") preservados.
2. Mantenha os 7 dias da semana (Segunda a Domingo).
3. Retorne EXCLUSIVAMENTE o array JSON atualizado, com as mesmas chaves ("dia", "modalidade", "titulo", "descricao", "duracao_ou_dist", "rpe_alvo", "concluido", "rpe_real", "feedback").
"""
                        resposta = gerar_resposta_ia(prompt_ajuste)
                        planilha_ajustada = extrair_json_planilha(resposta)
                        dados_atleta["planilha"] = planilha_ajustada
                        salvar_dados_usuario(usuario_input, dados_atleta)
                        st.success("Planilha ajustada com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao ajustar treino: {e}")

    # ------------------------------------------
    # ABA 4: EXPORTAÇÃO WHATSAPP E CALENDÁRIO (.ICS)
    # ------------------------------------------
    with tab_exportar:
        st.subheader("📅 Compartilhar e Exportar")

        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            st.markdown("### 📱 Resumo para WhatsApp")
            st.caption("Clique no ícone de copiar no canto superior direito da caixa abaixo:")
            texto_wpp = gerar_texto_whatsapp(usuario_input, semana_num, planilha_atual)
            st.code(texto_wpp, language="markdown")

        with col_exp2:
            st.markdown("### 🗓️ Sincronizar Agenda & Excel")
            st.caption("Importe seus treinos direto no Google Agenda, Apple Calendar ou planilhas:")

            ics_conteudo = gerar_arquivo_ics(usuario_input, semana_num, planilha_atual)
            st.download_button(
                label="📆 Baixar Calendário (.ics)",
                data=ics_conteudo,
                file_name=f"treinos_{usuario_input}_semana_{semana_num}.ics",
                mime="text/calendar",
                use_container_width=True
            )

            df_export = pd.DataFrame(planilha_atual)
            csv_conteudo = df_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📊 Baixar Planilha (.csv)",
                data=csv_conteudo,
                file_name=f"treinos_{usuario_input}_semana_{semana_num}.csv",
                mime="text/csv",
                use_container_width=True
            )
