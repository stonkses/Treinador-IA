import streamlit as st
from google import genai
from supabase import create_client, Client
import json
import pandas as pd
import io

# Configuração da página
st.set_page_config(
    page_title="Coach IA Endurance",
    page_icon="🏃‍♂️",
    layout="wide"
)

# Conexão com Supabase (Nuvem)
@st.cache_resource
def init_supabase() -> Client | None:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = init_supabase()

# Funções de persistência na nuvem
def carregar_dados_usuario(usuario: str) -> dict:
    usuario_limpo = usuario.strip().lower()
    if supabase:
        try:
            res = supabase.table("atletas").select("dados").eq("usuario", usuario_limpo).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["dados"]
        except Exception as e:
            st.sidebar.error(f"Erro ao carregar da nuvem: {e}")
    return {
        "perfil": None,
        "planilha": [],
        "historico_semanas": [],
        "semana_atual": 1
    }

def salvar_dados_usuario(usuario: str, dados: dict):
    usuario_limpo = usuario.strip().lower()
    if supabase:
        try:
            supabase.table("atletas").upsert({
                "usuario": usuario_limpo,
                "dados": dados
            }).execute()
        except Exception as e:
            st.error(f"Erro ao salvar na nuvem: {e}")

# Inicialização do cliente Gemini com fallback automático
def get_gemini_client():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        return genai.Client(api_key=api_key)
    except Exception:
        return None

def gerar_resposta_ia(prompt: str) -> str:
    client = get_gemini_client()
    if not client:
        raise ValueError("Chave GEMINI_API_KEY não encontrada nos Secrets.")
    
    modelos = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    ultimo_erro = None
    for modelo in modelos:
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=prompt
            )
            return response.text
        except Exception as e:
            ultimo_erro = e
            continue
    raise RuntimeError(f"Falha ao gerar resposta nos modelos disponíveis: {ultimo_erro}")

def extrair_json(texto: str) -> list:
    texto_limpo = texto.strip()
    if "```json" in texto_limpo:
        texto_limpo = texto_limpo.split("```json")[1].split("```")[0].strip()
    elif "```" in texto_limpo:
        texto_limpo = texto_limpo.split("```")[1].split("```")[0].strip()
    return json.loads(texto_limpo)

# --- BARRA LATERAL: PERFIL DE ACESSO ---
st.sidebar.header("👤 Perfil de Acesso")
nome_usuario = st.sidebar.text_input("Digite seu nome ou apelido:", placeholder="Ex: arthur")

if not nome_usuario.strip():
    st.title("🏃‍♂️ Coach IA - Treinos Adaptativos")
    st.info("👉 Digite seu **nome ou apelido** no menu lateral para carregar ou criar sua planilha individual.")
    st.stop()

usuario_id = nome_usuario.strip().lower()

# Status da IA e da Nuvem na barra lateral
if get_gemini_client():
    st.sidebar.success("✅ IA Conectada!")
else:
    st.sidebar.error("❌ IA Desconectada (verifique GEMINI_API_KEY)")

if supabase:
    st.sidebar.success("☁️ Nuvem Conectada!")
else:
    st.sidebar.warning("⚠️ Modo Temporário (Nuvem não configurada)")

# Carrega estado do usuário na sessão
if "usuario_ativo" not in st.session_state or st.session_state.usuario_ativo != usuario_id:
    st.session_state.usuario_ativo = usuario_id
    st.session_state.dados = carregar_dados_usuario(usuario_id)

dados = st.session_state.dados

st.sidebar.divider()
if st.sidebar.button("🗑️ Resetar Meus Treinos"):
    dados = {
        "perfil": None,
        "planilha": [],
        "historico_semanas": [],
        "semana_atual": 1
    }
    st.session_state.dados = dados
    salvar_dados_usuario(usuario_id, dados)
    st.rerun()

# --- CORPO PRINCIPAL ---
st.title("🏃‍♂️ Coach IA - Treinos Adaptativos")
st.caption(f"Atleta: **{nome_usuario.strip().title()}** | Ciclo Atual: Semana {dados['semana_atual']}")

aba1, aba2, aba3 = st.tabs(["📋 Planilha Atual", "✅ Registrar Treino", "🧠 Evolução & Próxima Semana"])

# ==========================================
# ABA 1: PLANILHA ATUAL / CONFIGURAÇÃO
# ==========================================
with aba1:
    if not dados["planilha"]:
        modo_inicio = st.radio(
            "Como você quer começar?",
            ["🆕 Criar planilha do zero com IA", "📥 Já tenho minha planilha (usar de base)"],
            horizontal=True
        )
        st.divider()

        if modo_inicio == "🆕 Criar planilha do zero com IA":
            st.subheader("Configurar Perfil do Atleta")
            esporte = st.selectbox("Qual esporte ou modalidade?", ["Corrida", "Ciclismo", "Triathlon", "Musculação", "Crossfit", "Natação", "Outro"])
            nivel = st.select_slider("Nível atual:", options=["Iniciante", "Intermediário", "Avançado", "Competitivo"])
            dias_semana = st.slider("Quantos dias por semana pode treinar?", 2, 7, 4)
            objetivo = st.text_input("Qual seu objetivo principal?", placeholder="Ex: Completar 10km, melhorar pace...")
            observacoes = st.text_area("Lesões, limitações ou equipamentos:", placeholder="Ex: Tenho relógio GPS, piscina 25m...")

            if st.button("🚀 Gerar Minha Planilha Inicial", type="primary"):
                if not objetivo.strip():
                    st.warning("Por favor, preencha seu objetivo principal.")
                else:
                    with st.spinner("A IA está montando sua planilha personalizada..."):
                        prompt = f"""
                        Você é um treinador de alta performance especialista em {esporte}.
                        Crie uma planilha de treino para a Semana 1 para um atleta com o seguinte perfil:
                        - Modalidade: {esporte}
                        - Nível: {nivel}
                        - Disponibilidade: {dias_semana} dias na semana
                        - Objetivo: {objetivo}
                        - Observações/Limitações: {observacoes or 'Nenhuma'}

                        Retorne EXCLUSIVAMENTE um array JSON válido (sem markdown ou texto extra) onde cada objeto representa um treino da semana com as exatas chaves:
                        - "dia": string (ex: "Segunda-feira", "Quarta-feira")
                        - "titulo": string (ex: "Rodagem Leve Z2", "Treino de Tiros")
                        - "descricao": string (detalhes de aquecimento, parte principal, paces/zonas/cargas e desaquecimento)
                        - "duracao_estimada": string (ex: "45 min" ou "8 km")
                        - "concluido": false
                        - "feedback": ""
                        - "rpe": 5
                        """
                        try:
                            resposta = gerar_resposta_ia(prompt)
                            planilha_gerada = extrair_json(resposta)
                            dados["perfil"] = {
                                "esporte": esporte,
                                "nivel": nivel,
                                "dias_semana": dias_semana,
                                "objetivo": objetivo,
                                "observacoes": observacoes
                            }
                            dados["planilha"] = planilha_gerada
                            salvar_dados_usuario(usuario_id, dados)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao gerar planilha: {e}")

        else:
            st.subheader("Importar Planilha Existente como Base")
            esporte_base = st.selectbox("Modalidade da planilha:", ["Corrida", "Ciclismo", "Triathlon", "Musculação", "Crossfit", "Natação", "Outro"])
            objetivo_base = st.text_input("Objetivo para a próxima evolução:", placeholder="Ex: Aumentar volume com segurança, baixar tempo nos 5km...")
            planilha_colada = st.text_area(
                "Cole aqui sua planilha atual (texto, tabela do Excel, resumo dos treinos):",
                height=200,
                placeholder="Ex:\nSeg: 6km leve pace 5:30\nQua: 8x400m forte\nSex: 5km regenerativo\nDom: 12km longo"
            )

            if st.button("🔄 Analisar e Gerar Planilha Evoluída", type="primary"):
                if not planilha_colada.strip():
                    st.warning("Cole sua planilha atual antes de continuar.")
                else:
                    with st.spinner("Analisando sua base e estruturando sua nova semana..."):
                        prompt = f"""
                        Você é um treinador especialista em {esporte_base}.
                        O atleta já possui a seguinte planilha/rotina atual:
                        \"\"\"
                        {planilha_colada}
                        \"\"\"
                        Objetivo do atleta: {objetivo_base or 'Evoluir condicionamento mantendo a estrutura base'}

                        Analise a rotina colada, preserve a estrutura de dias que funciona para ele e gere a versão evoluída/otimizada para esta semana.
                        Retorne EXCLUSIVAMENTE um array JSON válido com as exatas chaves:
                        - "dia": string
                        - "titulo": string
                        - "descricao": string
                        - "duracao_estimada": string
                        - "concluido": false
                        - "feedback": ""
                        - "rpe": 5
                        """
                        try:
                            resposta = gerar_resposta_ia(prompt)
                            planilha_gerada = extrair_json(resposta)
                            dados["perfil"] = {
                                "esporte": esporte_base,
                                "nivel": "Base Importada",
                                "dias_semana": len(planilha_gerada),
                                "objetivo": objetivo_base or "Evolução contínua",
                                "observacoes": "Gerado a partir de planilha importada"
                            }
                            dados["planilha"] = planilha_gerada
                            salvar_dados_usuario(usuario_id, dados)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao processar planilha: {e}")

    else:
        # Exibe a planilha ativa
        st.subheader(f"Treinos Programados — Semana {dados['semana_atual']}")
        for idx, treino in enumerate(dados["planilha"]):
            status_icon = "✅" if treino.get("concluido") else "⏳"
            with st.expander(f"{status_icon} {treino['dia']} — {treino['titulo']} ({treino['duracao_estimada']})", expanded=not treino.get("concluido")):
                st.write(treino["descricao"])
                if treino.get("concluido"):
                    st.success(f"Concluído | Esforço (RPE): {treino.get('rpe', '-')}/10 | Feedback: {treino.get('feedback') or 'Sem observações'}")

        st.divider()
        # Botões de Exportação (CSV e Texto)
        st.subheader("📥 Exportar Planilha")
        col1, col2 = st.columns(2)

        df_export = pd.DataFrame([
            {
                "Dia": t["dia"],
                "Treino": t["titulo"],
                "Duração/Volume": t["duracao_estimada"],
                "Descrição": t["descricao"],
                "Status": "Concluído" if t.get("concluido") else "Pendente",
                "RPE": t.get("rpe", ""),
                "Feedback": t.get("feedback", "")
            }
            for t in dados["planilha"]
        ])
        csv_bytes = df_export.to_csv(index=False, sep=";").encode("utf-8-sig")

        texto_linhas = [f"PLANILHA DE TREINO - {nome_usuario.strip().upper()} (SEMANA {dados['semana_atual']})\n" + "="*50]
        for t in dados["planilha"]:
            status = "[CONCLUÍDO]" if t.get("concluido") else "[PENDENTE]"
            texto_linhas.append(f"\n{t['dia']} - {t['titulo']} ({t['duracao_estimada']}) {status}\n{t['descricao']}")
        texto_completo = "\n".join(texto_linhas)

        with col1:
            st.download_button(
                label="📊 Baixar Planilha (CSV / Excel)",
                data=csv_bytes,
                file_name=f"planilha_{usuario_id}_semana_{dados['semana_atual']}.csv",
                mime="text/csv"
            )
        with col2:
            st.download_button(
                label="📄 Baixar Planilha (Texto .txt)",
                data=texto_completo,
                file_name=f"planilha_{usuario_id}_semana_{dados['semana_atual']}.txt",
                mime="text/plain"
            )

# ==========================================
# ABA 2: REGISTRAR TREINO
# ==========================================
with aba2:
    if not dados["planilha"]:
        st.info("Crie ou importe sua planilha na aba **Planilha Atual** primeiro.")
    else:
        st.subheader("Registrar Execução e Sensação de Esforço")
        opcoes_treinos = [f"{i+1}. {t['dia']} - {t['titulo']}" for i, t in enumerate(dados["planilha"])]
        escolha = st.selectbox("Selecione o treino realizado:", opcoes_treinos)
        indice = opcoes_treinos.index(escolha)
        treino_sel = dados["planilha"][indice]

        concluido = st.checkbox("Marcar treino como concluído", value=treino_sel.get("concluido", False))
        rpe = st.slider("Percepção Subjetiva de Esforço (RPE 1 = Muito Fácil, 10 = Máximo):", 1, 10, int(treino_sel.get("rpe", 5)))
        feedback = st.text_area("Como você se sentiu? (cansaço, dores, ritmo atingido, falta de tempo...):", value=treino_sel.get("feedback", ""))

        if st.button("💾 Salvar Registro", type="primary"):
            dados["planilha"][indice]["concluido"] = concluido
            dados["planilha"][indice]["rpe"] = rpe
            dados["planilha"][indice]["feedback"] = feedback
            salvar_dados_usuario(usuario_id, dados)
            st.success("Registro salvo na nuvem com sucesso!")
            st.rerun()

# ==========================================
# ABA 3: EVOLUÇÃO & PRÓXIMA SEMANA
# ==========================================
with aba3:
    if not dados["planilha"]:
        st.info("Crie ou importe sua planilha na aba **Planilha Atual** primeiro.")
    else:
        st.subheader(f"Fechar Semana {dados['semana_atual']} e Gerar Semana {dados['semana_atual'] + 1}")
        st.write("A IA vai analisar quais treinos você completou, seu nível de cansaço (RPE) e seus comentários para ajustar a carga da próxima semana.")

        ajuste_extra = st.text_area("Algum pedido especial para a próxima semana?", placeholder="Ex: Vou viajar sexta-feira, quero focar mais em subidas...")

        if st.button("🧠 Gerar Próxima Semana Adaptada", type="primary"):
            with st.spinner("Analisando seu desempenho semanal e calculando a progressão..."):
                resumo_semana = json.dumps(dados["planilha"], ensure_ascii=False, indent=2)
                perfil_str = json.dumps(dados["perfil"], ensure_ascii=False)
                prompt = f"""
                Você é um treinador de alta performance.
                Perfil do atleta: {perfil_str}
                Desempenho na Semana {dados['semana_atual']}:
                {resumo_semana}

                Pedidos adicionais para a Semana {dados['semana_atual'] + 1}: {ajuste_extra or 'Nenhum'}

                Com base nos treinos concluídos ou pulados, no RPE e nos feedbacks:
                - Se o RPE esteve muito alto (8-10) ou houve cansaço/dor, reduza levemente a intensidade ou aplique semana regenerativa.
                - Se o atleta concluiu bem com RPE controlado (4-7), aplique progressão gradual de volume ou intensidade.

                Retorne EXCLUSIVAMENTE um array JSON válido com a planilha da Semana {dados['semana_atual'] + 1}, contendo as chaves:
                - "dia": string
                - "titulo": string
                - "descricao": string
                - "duracao_estimada": string
                - "concluido": false
                - "feedback": ""
                - "rpe": 5
                """
                try:
                    resposta = gerar_resposta_ia(prompt)
                    nova_planilha = extrair_json(resposta)
                    dados["historico_semanas"].append({
                        "semana": dados["semana_atual"],
                        "planilha": dados["planilha"]
                    })
                    dados["semana_atual"] += 1
                    dados["planilha"] = nova_planilha
                    salvar_dados_usuario(usuario_id, dados)
                    st.success(f"Semana {dados['semana_atual']} gerada e salva na nuvem!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao gerar próxima semana: {e}")
