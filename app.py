import streamlit as st
import json
import os
import time
from datetime import datetime
from google import genai

st.set_page_config(page_title="Coach IA Endurance", page_icon="🏃‍♂️", layout="centered")

# ================= IDENTIFICAÇÃO DO ATLETA (MULTI-USUÁRIO) =================
st.sidebar.header("👤 Perfil de Acesso")
usuario_input = st.sidebar.text_input("Digite seu nome ou apelido:", placeholder="Ex: arthur").strip().lower()
usuario_limpo = "".join(c for c in usuario_input if c.isalnum())

if not usuario_limpo:
    st.title("🏃‍♂️ Coach IA - Treinos Adaptativos")
    st.info("👈 Digite seu **nome ou apelido** no menu lateral para carregar ou criar sua planilha individual.")
    st.stop()

ARQUIVO_DADOS = f"dados_{usuario_limpo}.json"
ARQUIVO_CHAVE = "config_api.json"

def carregar_dados():
    if os.path.exists(ARQUIVO_DADOS):
        with open(ARQUIVO_DADOS, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"perfil": {}, "planilha_atual": "", "semana": 1, "historico": []}

def salvar_dados(dados):
    with open(ARQUIVO_DADOS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)

def carregar_chave():
    # 1. Tenta ler dos Secrets da nuvem (Streamlit Cloud)
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    # 2. Tenta ler do arquivo local
    if os.path.exists(ARQUIVO_CHAVE):
        with open(ARQUIVO_CHAVE, "r", encoding="utf-8") as f:
            return json.load(f).get("api_key", "")
    return ""

def salvar_chave(chave):
    with open(ARQUIVO_CHAVE, "w", encoding="utf-8") as f:
        json.dump({"api_key": chave}, f)

def chamar_ia_seguro(client, prompt):
    modelos = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
    ultimo_erro = None
    for modelo in modelos:
        for tentativa in range(2):
            try:
                response = client.models.generate_content(
                    model=modelo,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                ultimo_erro = e
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    time.sleep(2)
                    continue
                break
    raise ultimo_erro

dados = carregar_dados()
chave_salva = carregar_chave()

st.title("🏃‍♂️ Coach IA - Treinos Adaptativos")
st.caption(f"Atleta: **{usuario_limpo.capitalize()}** | Ciclo Atual: Semana {dados.get('semana', 1)}")

# ================= BARRA LATERAL: CHAVE E RESET =================
if chave_salva:
    api_key = chave_salva
    st.sidebar.success("✅ IA Conectada!")
else:
    st.sidebar.divider()
    api_key_input = st.sidebar.text_input("🔑 Chave API do Gemini:", type="password")
    api_key = api_key_input.strip().replace('"', '').replace("'", "")
    if st.sidebar.button("💾 Salvar Chave"):
        if api_key:
            salvar_chave(api_key)
            st.rerun()

st.sidebar.divider()
if st.sidebar.button("🗑️ Resetar Meus Treinos"):
    if os.path.exists(ARQUIVO_DADOS):
        os.remove(ARQUIVO_DADOS)
    st.rerun()

aba1, aba2, aba3 = st.tabs(["📋 Planilha Atual", "✅ Registrar Treino", "🧠 Evolução & Próxima Semana"])

# ================= ABA 1: GERAR DO ZERO OU USAR BASE =================
with aba1:
    if not dados["planilha_atual"]:
        modo = st.radio(
            "Como você quer começar?",
            ["🆕 Criar planilha do zero com IA", "📥 Já tenho minha planilha (usar de base)"],
            horizontal=True
        )
        st.divider()

        if modo == "📥 Já tenho minha planilha (usar de base)":
            st.subheader("Gerar Nova Planilha a Partir da Sua Base")
            esporte_imp = st.selectbox(
                "Qual esporte ou modalidade?",
                ["Triatlo (Natação + Bike + Corrida)", "Corrida", "Ciclismo", "Natação", "Duatlo", "Outro"]
            )
            if esporte_imp == "Outro":
                esporte_imp = st.text_input("Digite o esporte:")

            objetivo_imp = st.text_input("Qual seu novo objetivo ou foco?", placeholder="Ex: Triatlo SuperSprint, 5km sub 27min, aumentar volume...")
            equipamentos_imp = st.text_input("Equipamentos / observações (opcional):", placeholder="Ex: Garmin Venu 4, fita cardíaca, bike...")
            planilha_base = st.text_area(
                "Cole aqui a sua planilha atual/anterior para servir de base:",
                height=220,
                placeholder="Ex:\nSegunda: Corrida leve 5km Z2\nTerça: Bike 20km ritmo moderado\nQuarta: Natação 1000m técnica..."
            )

            if st.button("🚀 Gerar Nova Planilha com Base Nessa", type="primary"):
                if not api_key:
                    st.warning("⚠️ Chave da API não configurada!")
                elif not planilha_base.strip():
                    st.warning("⚠️ Cole o texto da sua planilha de base antes de gerar.")
                else:
                    try:
                        client = genai.Client(api_key=api_key)
                        prompt_base = (
                            f"Você é um treinador especialista em esportes de endurance. "
                            f"O atleta já possui uma planilha de treino e quer que você a use como BASE "
                            f"(respeitando o nível de condicionamento, distribuição de dias e modalidades atuais) "
                            f"para montar uma NOVA planilha otimizada para a SEMANA 1 do novo ciclo.\n\n"
                            f"Esporte: {esporte_imp}\n"
                            f"Objetivo atual: {objetivo_imp or 'Evoluir condicionamento mantendo a estrutura base'}\n"
                            f"Equipamentos/Observações: {equipamentos_imp}\n"
                            f"PLANILHA BASE DO ATLETA:\n{planilha_base.strip()}\n\n"
                            f"Comece com um breve resumo ('### 🎯 Ajustes feitos sobre sua base') explicando o que você manteve e o que evoluiu. "
                            f"Depois organize a nova planilha em uma tabela Markdown clara com: Dia, Modalidade, Treino Detalhado e Foco."
                        )
                        with st.spinner("Analisando sua planilha base e montando a nova..."):
                            texto_resposta = chamar_ia_seguro(client, prompt_base)
                            dados["perfil"] = {
                                "esporte": esporte_imp,
                                "nivel": "Baseado na planilha própria",
                                "dias_semana": "Conforme planilha base",
                                "objetivo": objetivo_imp or "Evoluir planilha base",
                                "observacoes": equipamentos_imp
                            }
                            dados["planilha_atual"] = texto_resposta
                            dados["semana"] = 1
                            salvar_dados(dados)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao conectar com a IA: {e}")

        else:
            st.subheader("Configurar Perfil do Atleta")
            esporte = st.selectbox(
                "Qual esporte ou modalidade?",
                ["Corrida", "Triatlo (Natação + Bike + Corrida)", "Ciclismo", "Natação", "Duatlo", "Outro"]
            )
            if esporte == "Outro":
                esporte = st.text_input("Digite o esporte:")

            nivel = st.select_slider("Nível atual:", options=["Iniciante", "Intermediário", "Avançado"])
            dias_semana = st.slider("Quantos dias por semana pode treinar?", 2, 7, 4)
            objetivo = st.text_input("Qual seu objetivo principal?", placeholder="Ex: Completar 10km, melhorar pace...")
            observacoes = st.text_area("Lesões, limitações ou equipamentos:", placeholder="Ex: Tenho relógio GPS, piscina 25m...")

            if st.button("🚀 Gerar Minha Primeira Semana", type="primary"):
                if not api_key:
                    st.warning("⚠️ Chave da API não configurada!")
                elif not objetivo:
                    st.warning("⚠️ Preencha qual é o seu objetivo principal.")
                else:
                    try:
                        client = genai.Client(api_key=api_key)
                        prompt = (
                            f"Você é um treinador especialista em esportes de endurance. "
                            f"Crie uma planilha de treinos para a SEMANA 1: "
                            f"Esporte: {esporte} | Nível: {nivel} | Dias/semana: {dias_semana} | "
                            f"Objetivo: {objetivo} | Observações: {observacoes}. "
                            f"Organize em uma tabela Markdown clara com: Dia, Modalidade, Treino Detalhado e Foco."
                        )
                        with st.spinner("Montando sua planilha personalizada..."):
                            texto_resposta = chamar_ia_seguro(client, prompt)
                            dados["perfil"] = {
                                "esporte": esporte,
                                "nivel": nivel,
                                "dias_semana": dias_semana,
                                "objetivo": objetivo,
                                "observacoes": observacoes
                            }
                            dados["planilha_atual"] = texto_resposta
                            dados["semana"] = 1
                            salvar_dados(dados)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao conectar com a IA: {e}")
    else:
        st.subheader(f"📅 Planilha - Semana {dados.get('semana', 1)}")
        st.markdown(dados["planilha_atual"])

# ================= ABA 2: REGISTRAR TREINO FEITO =================
with aba2:
    st.subheader("Diário de Treino")
    if not dados["planilha_atual"]:
        st.info("Gere sua planilha na aba anterior antes de registrar treinos.")
    else:
        with st.form("form_treino", clear_on_submit=True):
            dia_treino = st.selectbox("Dia da semana do treino:", ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"])
            modalidade_feita = st.text_input("Modalidade realizada:", value=dados["perfil"].get("esporte", ""))
            realizado = st.text_area("O que você realmente fez? (Distância, tempo, pace, watts...)", placeholder="Ex: Corri 5km em 27min30s ou Pulei o treino.")
            pse = st.slider("Percepção de Esforço (1 = Muito leve | 10 = Exaustão máxima):", 1, 10, 6)
            sensacao = st.text_input("Como seu corpo respondeu? (Dores, fadiga, sobrou energia?)", placeholder="Ex: Senti a perna pesada no final.")
            
            enviado = st.form_submit_button("💾 Salvar Treino no Histórico", type="primary")
            if enviado:
                if not realizado:
                    st.warning("Descreva o que foi realizado no treino.")
                else:
                    registro = {
                        "data": datetime.now().strftime("%d/%m/%Y"),
                        "semana": dados.get("semana", 1),
                        "dia": dia_treino,
                        "modalidade": modalidade_feita,
                        "realizado": realizado,
                        "pse": pse,
                        "sensacao": sensacao
                    }
                    dados["historico"].append(registro)
                    salvar_dados(dados)
                    st.success("Treino salvo! A IA usará esse dado para ajustar sua próxima semana.")

    if dados["historico"]:
        st.divider()
        st.subheader("📊 Histórico Recente")
        for item in reversed(dados["historico"][-5:]):
            st.markdown(f"**Semana {item['semana']} - {item['dia']} ({item['data']})** | Esforço (PSE): **{item['pse']}/10**")
            st.write(f"• **Feito:** {item['realizado']}")
            if item['sensacao']:
                st.caption(f"💬 Sensação: {item['sensacao']}")
            st.markdown("---")

# ================= ABA 3: IA ANALISA E ADAPTA A CARGA =================
with aba3:
    st.subheader("🧠 Treinador Adaptativo")
    st.write("A IA analisa seus treinos realizados, seu nível de cansaço (PSE) e decide se aumenta, mantém ou reduz a intensidade.")

    if not dados["planilha_atual"]:
        st.info("Gere sua planilha primeiro.")
    elif not dados["historico"]:
        st.warning("⚠️ Registre pelo menos um treino na aba 'Registrar Treino' para a IA ter dados.")
    else:
        if st.button("🔄 Analisar Desempenho e Gerar Próxima Semana", type="primary"):
            if not api_key:
                st.warning("⚠️ Chave da API não configurada!")
            else:
                try:
                    client = genai.Client(api_key=api_key)
                    proxima_semana = dados.get("semana", 1) + 1
                    
                    treinos_semana = [t for t in dados["historico"] if t["semana"] == dados.get("semana", 1)]
                    if not treinos_semana:
                        treinos_semana = dados["historico"][-5:]

                    prompt_adaptativo = (
                        f"Você é um treinador de elite especialista em esportes de endurance. "
                        f"Analise o desempenho na Semana {dados.get('semana', 1)} e monte a SEMANA {proxima_semana} "
                        f"respeitando a estrutura e o estilo da planilha que o atleta já segue.\n"
                        f"PERFIL: {json.dumps(dados['perfil'], ensure_ascii=False)}\n"
                        f"PLANILHA ANTERIOR: {dados['planilha_atual']}\n"
                        f"TREINOS REALIZADOS: {json.dumps(treinos_semana, ensure_ascii=False)}\n\n"
                        f"REGRAS DE DECISÃO:\n"
                        f"- Se PSE médio > 8 ou relato de dor/fadiga: REDUZA volume/intensidade em 15% a 25% e foque em regenerativo.\n"
                        f"- Se PSE médio entre 5 e 7: APLIQUE PROGRESSÃO GRADUAL (+5% a 10%).\n"
                        f"- Se PSE médio < 5: AUMENTE o estímulo com intervalados ou maior volume.\n\n"
                        f"Comece com '### 📋 Análise do Treinador' explicando se decidiu AUMENTAR, MANTER ou REDUZIR a carga. "
                        f"Depois mostre a tabela Markdown da SEMANA {proxima_semana} (Dia, Modalidade, Treino Detalhado, Foco)."
                    )

                    with st.spinner("Analisando fadiga, ritmo e recalculando cargas..."):
                        texto_resposta = chamar_ia_seguro(client, prompt_adaptativo)
                        dados["planilha_atual"] = texto_resposta
                        dados["semana"] = proxima_semana
                        salvar_dados(dados)
                        st.success(f"Semana {proxima_semana} gerada com sucesso!")
                        st.markdown(texto_resposta)

                except Exception as e:
                    st.error(f"Erro ao gerar adaptação: {e}")
