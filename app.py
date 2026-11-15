import streamlit as st
import json
from datetime import timedelta

from config import (
    VERSAO_APP,
    DIAS_SEMANA_ORDEM,
    SENSACOES_OPCOES,
    CSS_CUSTOMIZADO
)
from database import (
    estrutura_padrao,
    gerar_hash_pin,
    verificar_pin,
    buscar_registro_bruto,
    salvar_dados_usuario
)
from ai_coach import (
    gerar_json_ia,
    extrair_e_validar_planilha
)
from parsers import processar_arquivo_atividade
from utils import (
    hoje_br,
    sanitizar_html,
    saudacao_horario,
    obter_proxima_prova,
    calcular_fase_periodizacao,
    resumo_provas_para_ia,
    gerar_texto_whatsapp,
    gerar_arquivo_ics
)

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Treinador • Seu Plano de Treino",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.markdown(CSS_CUSTOMIZADO, unsafe_allow_html=True)

# ==========================================
# CALLBACKS DE PERSISTÊNCIA IMEDIATA (BUG 1.1 / 1.2)
# ==========================================
def salvar_campo_treino(idx: int, campo: str, widget_key: str):
    usuario = st.session_state.get("usuario_atual")
    dados = st.session_state.get("dados_atleta")
    if not usuario or not dados:
        return
    planilha = dados.get("planilha", [])
    if 0 <= idx < len(planilha) and widget_key in st.session_state:
        planilha[idx][campo] = st.session_state[widget_key]
        dados["planilha"] = planilha
        salvar_dados_usuario(usuario, dados)

# ==========================================
# BARRA LATERAL E AUTENTICAÇÃO (BUG 2.1)
# ==========================================
with st.sidebar:
    st.markdown("### 🏃 Seu Treinador")
    st.caption("Planejamento simples, adaptado à sua rotina.")
    st.divider()

    usuario_input = st.text_input(
        "Seu nome ou apelido",
        value=st.session_state.get("usuario_digitado", ""),
        placeholder="Ex: joao"
    ).strip().lower()
    st.session_state["usuario_digitado"] = usuario_input

    if not usuario_input:
        st.info("Digite seu nome acima para entrar.")
        st.caption(f"Versão {VERSAO_APP}")
        st.stop()

    # Se mudou o nome digitado, reseta o estado de autenticação
    if st.session_state.get("usuario_verificado") != usuario_input:
        st.session_state["autenticado"] = False
        st.session_state["usuario_verificado"] = usuario_input
        st.session_state["registro_pendente"] = buscar_registro_bruto(usuario_input)

    registro_pendente = st.session_state.get("registro_pendente")

    if not st.session_state.get("autenticado"):
        if registro_pendente is None:
            st.markdown("**Criar novo perfil**")
            pin_novo = st.text_input(
                "Crie um PIN de acesso (4 dígitos)",
                type="password",
                max_chars=8,
                placeholder="Ex: 1234",
                key="pin_criar_input"
            )
            if st.button("Criar e entrar", type="primary", use_container_width=True):
                if len(pin_novo.strip()) < 4:
                    st.warning("Escolha um PIN com pelo menos 4 caracteres.")
                else:
                    novo_dados = estrutura_padrao(pin_hash=gerar_hash_pin(usuario_input, pin_novo))
                    salvar_dados_usuario(usuario_input, novo_dados)
                    st.session_state["usuario_atual"] = usuario_input
                    st.session_state["dados_atleta"] = novo_dados
                    st.session_state["autenticado"] = True
                    st.rerun()
        else:
            hash_existente = registro_pendente.get("pin_hash", "")
            if not hash_existente:
                # Migração suave para contas antigas criadas antes da v2.1
                st.markdown("**Proteja seu perfil**")
                st.caption("Defina um PIN para proteger sua planilha.")
                pin_migrar = st.text_input(
                    "Defina seu PIN (mín. 4 caracteres)",
                    type="password",
                    max_chars=8,
                    key="pin_migrar_input"
                )
                if st.button("Salvar PIN e entrar", type="primary", use_container_width=True):
                    if len(pin_migrar.strip()) < 4:
                        st.warning("Escolha um PIN com pelo menos 4 caracteres.")
                    else:
                        registro_pendente["pin_hash"] = gerar_hash_pin(usuario_input, pin_migrar)
                        salvar_dados_usuario(usuario_input, registro_pendente)
                        st.session_state["usuario_atual"] = usuario_input
                        st.session_state["dados_atleta"] = registro_pendente
                        st.session_state["autenticado"] = True
                        st.rerun()
            else:
                pin_login = st.text_input(
                    "Digite seu PIN de acesso",
                    type="password",
                    max_chars=8,
                    key="pin_login_input"
                )
                if st.button("Entrar", type="primary", use_container_width=True):
                    if verificar_pin(usuario_input, pin_login, hash_existente):
                        st.session_state["usuario_atual"] = usuario_input
                        st.session_state["dados_atleta"] = registro_pendente
                        st.session_state["autenticado"] = True
                        st.rerun()
                    else:
                        st.error("PIN incorreto.")

        st.divider()
        st.caption(f"Versão {VERSAO_APP}")
        st.stop()

    # Usuário autenticado
    dados_atleta = st.session_state["dados_atleta"]
    perfil = dados_atleta.get("perfil", {})
    provas_salvas = dados_atleta.get("provas", [])

    st.caption(f"Conectado como **{usuario_input.capitalize()}**")
    if st.button("Sair", use_container_width=True):
        st.session_state["autenticado"] = False
        st.session_state["usuario_atual"] = ""
        st.session_state["dados_atleta"] = {}
        st.rerun()

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
        st.caption("Apaga sua planilha atual e o histórico mantendo seu PIN.")
        if st.button("Apagar e recomeçar", use_container_width=True):
            pin_preservado = dados_atleta.get("pin_hash", "")
            st.session_state["dados_atleta"] = estrutura_padrao(pin_hash=pin_preservado)
            salvar_dados_usuario(usuario_input, st.session_state["dados_atleta"])
            st.rerun()

    st.divider()
    st.caption(f"Versão {VERSAO_APP}")

# ==========================================
# CABEÇALHO HUMANO SANITIZADO CONTRA XSS (BUG 2.2)
# ==========================================
semana_num = dados_atleta.get("semana_atual", 1)
esporte_atual = perfil.get("esporte", "Treino Personalizado")
objetivo_atual = perfil.get("objetivo", "Evoluir com consistência")
proxima_prova = obter_proxima_prova(provas_salvas)

nome_seguro = sanitizar_html(usuario_input.capitalize())
esporte_seguro = sanitizar_html(esporte_atual)
objetivo_seguro = sanitizar_html(objetivo_atual)

if proxima_prova:
    dias_f = proxima_prova["dias_restantes"]
    fase_nome, fase_desc = calcular_fase_periodizacao(dias_f)
    prova_nome_seguro = sanitizar_html(proxima_prova["nome"])
    prova_mod_seguro = sanitizar_html(proxima_prova["modalidade"])

    texto_dias = "É hoje! Boa prova!" if dias_f == 0 else (
        "Falta 1 dia para a prova" if dias_f == 1 else f"Faltam {dias_f} dias para {prova_nome_seguro}"
    )
    subtitulo_topo = f"{texto_dias} ({prova_mod_seguro}) • {sanitizar_html(fase_desc)}"
    pill_html = f'<div class="pill-fase">Semana {semana_num} • {sanitizar_html(fase_nome)} • {VERSAO_APP}</div>'
else:
    subtitulo_topo = f"{esporte_seguro} • Foco: {objetivo_seguro}"
    pill_html = f'<div class="pill-fase">Semana {semana_num} de treino • {VERSAO_APP}</div>'

st.markdown(f"""
<div class="welcome-card">
    <div class="welcome-title">{saudacao_horario()}, {nome_seguro}! 👋</div>
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
            prova_init_data = st.date_input("Data da prova", value=hoje_br() + timedelta(days=45), min_value=hoje_br(), key="p_init_data")

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
1. Retorne os 7 dias da semana na ordem exata: Segunda, Terça, Quarta, Quinta, Sexta, Sábado, Domingo.
2. Coloque treino APENAS nos dias disponíveis ({', '.join(dias_selecionados)}). Nos outros dias, use "modalidade": "Descanso" e "titulo": "Dia de descanso".
3. Escreva as descrições em linguagem humana, clara e encorajadora (aquecimento, treino principal e volta à calma).
4. Retorne EXCLUSIVAMENTE um array JSON com 7 objetos contendo as chaves:
   "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist"
"""
                        resposta = gerar_json_ia(prompt)
                        nova_planilha = extrair_e_validar_planilha(resposta)
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

Retorne EXCLUSIVAMENTE um array JSON com 7 objetos (Segunda a Domingo) e as chaves:
"dia", "modalidade", "titulo", "descricao", "duracao_ou_dist"
"""
                        resposta = gerar_json_ia(prompt)
                        nova_planilha = extrair_e_validar_planilha(resposta)
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
                        k_conc = f"conc_{semana_num}_{i}"
                        st.checkbox(
                            "Já fiz esse treino",
                            value=item.get("concluido", False),
                            key=k_conc,
                            on_change=salvar_campo_treino,
                            args=(i, "concluido", k_conc)
                        )

                    with c2:
                        k_sens = f"sens_{semana_num}_{i}"
                        idx_sens = (
                            SENSACOES_OPCOES.index(item.get("sensacao", "Ainda não fiz"))
                            if item.get("sensacao") in SENSACOES_OPCOES else 0
                        )
                        st.selectbox(
                            "Como você se sentiu?",
                            options=SENSACOES_OPCOES,
                            index=idx_sens,
                            key=k_sens,
                            on_change=salvar_campo_treino,
                            args=(i, "sensacao", k_sens)
                        )

                    k_fb = f"fb_{semana_num}_{i}"
                    st.text_input(
                        "Anotações sobre o treino (opcional)",
                        value=item.get("feedback", ""),
                        placeholder="Ex: Consegui manter o ritmo no final, me senti bem...",
                        key=k_fb,
                        on_change=salvar_campo_treino,
                        args=(i, "feedback", k_fb)
                    )

                    arquivo_up = st.file_uploader(
                        "Enviar arquivo do Garmin ou Strava (.fit, .tcx, .gpx)",
                        type=["fit", "tcx", "gpx"],
                        key=f"up_{semana_num}_{i}"
                    )
                    if arquivo_up is not None:
                        try:
                            resumo_arq, arq_hash = processar_arquivo_atividade(arquivo_up)
                            if planilha_atual[i].get("arquivo_hash") != arq_hash:
                                planilha_atual[i]["dados_arquivo"] = resumo_arq
                                planilha_atual[i]["arquivo_hash"] = arq_hash
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
                                "data_fechamento": hoje_br().strftime("%d/%m/%Y"),
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
- Retorne EXCLUSIVAMENTE um array JSON com 7 objetos (Segunda a Domingo) e as chaves: "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist".
"""
                            resposta = gerar_json_ia(prompt)
                            proxima_planilha = extrair_e_validar_planilha(resposta)

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
                nova_prova_data = st.date_input("Data", value=hoje_br() + timedelta(days=30), min_value=hoje_br())

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
            hoje = hoje_br()
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
1. Ajuste APENAS os dias necessários para atender o aluno, mantendo intactos os treinos já feitos ("concluido", "sensacao", "feedback", "dados_arquivo", "arquivo_hash").
2. Mantenha os 7 dias da semana (Segunda a Domingo).
3. Retorne EXCLUSIVAMENTE o array JSON atualizado com 7 objetos e as chaves: "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist", "concluido", "sensacao", "feedback", "dados_arquivo", "arquivo_hash".
"""
                        resposta = gerar_json_ia(prompt_ajuste)
                        planilha_ajustada = extrair_e_validar_planilha(resposta)
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
