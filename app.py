import json
from datetime import timedelta, date
import streamlit as st

from config import (
    APP_VERSION,
    DIAS_SEMANA,
    SENSACOES,
    MODALIDADES,
    APP_CSS
)
from database import (
    validar_username,
    default_athlete_data,
    hash_pin,
    verificar_pin,
    checar_bloqueio_login,
    registrar_falha_login,
    limpar_falhas_login,
    fetch_athlete,
    save_athlete
)
from ai_coach import (
    sanitize_prompt_input,
    request_plan_json,
    evaluate_uploaded_activity,
    parse_and_validate_week,
    parse_next_week_with_feedback
)
from parsers import parse_activity_file
from utils import (
    today_br,
    esc,
    greeting_br,
    get_next_race,
    get_periodization_phase,
    compute_pace_zones,
    build_races_context,
    format_whatsapp_plan,
    build_plan_pdf,
    build_ics_calendar
)

st.set_page_config(
    page_title="Treinador • Seu Plano de Treino",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded"
)
st.markdown(APP_CSS, unsafe_allow_html=True)


def persist_workout_field(idx: int, field: str, widget_key: str):
    usuario = st.session_state.get("usuario_atual")
    dados = st.session_state.get("dados_atleta")
    if not usuario or not dados:
        return
    planilha = dados.get("planilha", [])
    if 0 <= idx < len(planilha) and widget_key in st.session_state:
        val = st.session_state[widget_key]
        if isinstance(val, str):
            val = val[:600]
        planilha[idx][field] = val
        dados["planilha"] = planilha
        save_athlete(usuario, dados)


with st.sidebar:
    st.markdown("### 🏃 Seu Treinador")
    st.caption("Planejamento simples, adaptado à sua rotina.")
    st.divider()

    raw_user = st.text_input(
        "Seu nome ou apelido",
        value=st.session_state.get("usuario_digitado", ""),
        max_chars=24,
        placeholder="Ex: joao"
    )
    st.session_state["usuario_digitado"] = raw_user

    if not raw_user.strip():
        st.info("Digite seu nome acima para entrar.")
        st.caption(f"Versão {APP_VERSION}")
        st.stop()

    usuario_input = validar_username(raw_user)
    if not usuario_input:
        st.warning("Use apenas letras sem acento, números, ponto ou underline (2 a 24 caracteres).")
        st.caption(f"Versão {APP_VERSION}")
        st.stop()

    if st.session_state.get("usuario_verificado") != usuario_input:
        st.session_state["autenticado"] = False
        st.session_state["usuario_verificado"] = usuario_input
        st.session_state["registro_pendente"] = fetch_athlete(usuario_input)

    registro_pendente = st.session_state.get("registro_pendente")

    if not st.session_state.get("autenticado"):
        tempo_bloqueio = checar_bloqueio_login(usuario_input)
        if tempo_bloqueio > 0:
            st.error(f"Muitas tentativas incorretas. Tente novamente em {tempo_bloqueio}s.")
            st.stop()

        if registro_pendente is None:
            st.markdown("**Criar novo perfil**")
            pin_novo = st.text_input(
                "Crie um PIN de acesso (4 a 8 dígitos)",
                type="password",
                max_chars=8,
                placeholder="Ex: 1234",
                key="pin_criar_input"
            )
            if st.button("Criar e entrar", type="primary", use_container_width=True):
                if len(pin_novo.strip()) < 4:
                    st.warning("Escolha um PIN com pelo menos 4 caracteres.")
                else:
                    novo_dados = default_athlete_data(pin_hash=hash_pin(usuario_input, pin_novo))
                    save_athlete(usuario_input, novo_dados)
                    st.session_state["usuario_atual"] = usuario_input
                    st.session_state["dados_atleta"] = novo_dados
                    st.session_state["autenticado"] = True
                    st.rerun()
        else:
            hash_existente = registro_pendente.get("pin_hash", "")
            if not hash_existente:
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
                        registro_pendente["pin_hash"] = hash_pin(usuario_input, pin_migrar)
                        save_athlete(usuario_input, registro_pendente)
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
                    valido, migrar_hash = verificar_pin(usuario_input, pin_login, hash_existente)
                    if valido:
                        limpar_falhas_login(usuario_input)
                        if migrar_hash:
                            registro_pendente["pin_hash"] = hash_pin(usuario_input, pin_login)
                            save_athlete(usuario_input, registro_pendente)
                        st.session_state["usuario_atual"] = usuario_input
                        st.session_state["dados_atleta"] = registro_pendente
                        st.session_state["autenticado"] = True
                        st.rerun()
                    else:
                        restantes = registrar_falha_login(usuario_input)
                        if restantes > 0:
                            st.error(f"PIN incorreto. Restam {restantes} tentativas.")
                        else:
                            st.error("PIN bloqueado temporariamente por segurança.")

        st.divider()
        st.caption(f"Versão {APP_VERSION}")
        st.stop()

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
        options=DIAS_SEMANA,
        default=[d for d in dias_salvos if d in DIAS_SEMANA],
        label_visibility="collapsed"
    )
    dias_selecionados = [d for d in DIAS_SEMANA if d in dias_selecionados]

    if dias_selecionados != dias_salvos and perfil:
        dados_atleta["perfil"]["dias_disponiveis"] = dias_selecionados
        save_athlete(usuario_input, dados_atleta)

    with st.expander("⏱️ Tempo base 5 km (Zonas de Ritmo)"):
        st.caption("Se ainda não tem prova passada cadastrada, informe seu tempo nos 5 km para calcular seus ritmos.")
        tempo_5k_in = st.text_input(
            "Tempo nos 5 km",
            value=perfil.get("tempo_5k", ""),
            max_chars=20,
            placeholder="Ex: 25:30",
            key="base_5k_input"
        )
        if st.button("Salvar tempo base", use_container_width=True):
            dados_atleta.setdefault("perfil", {})["tempo_5k"] = tempo_5k_in.strip()[:20]
            save_athlete(usuario_input, dados_atleta)
            st.success("Zonas atualizadas!")
            st.rerun()

    st.divider()
    with st.expander("Alterar meu PIN"):
        pin_atual_in = st.text_input("PIN atual", type="password", max_chars=8, key="pin_old")
        pin_novo_in = st.text_input("Novo PIN (mín. 4 caracteres)", type="password", max_chars=8, key="pin_new")
        if st.button("Atualizar PIN", use_container_width=True):
            ok, _ = verificar_pin(usuario_input, pin_atual_in, dados_atleta.get("pin_hash", ""))
            if not ok:
                st.error("PIN atual incorreto.")
            elif len(pin_novo_in.strip()) < 4:
                st.warning("O novo PIN precisa ter pelo menos 4 caracteres.")
            else:
                dados_atleta["pin_hash"] = hash_pin(usuario_input, pin_novo_in)
                save_athlete(usuario_input, dados_atleta)
                st.success("PIN atualizado!")

    with st.expander("Recomeçar do zero"):
        st.caption("Apaga sua planilha atual e o histórico mantendo seu PIN.")
        if st.button("Apagar e recomeçar", use_container_width=True):
            pin_preservado = dados_atleta.get("pin_hash", "")
            st.session_state["dados_atleta"] = default_athlete_data(pin_hash=pin_preservado)
            save_athlete(usuario_input, st.session_state["dados_atleta"])
            st.rerun()

    st.divider()
    st.caption(f"Versão {APP_VERSION}")

# ==========================================
# CABEÇALHO DO ATLETA + ZONAS
# ==========================================
semana_num = dados_atleta.get("semana_atual", 1)
esporte_atual = perfil.get("esporte", "Treino Personalizado")
objetivo_atual = perfil.get("objetivo", "Evoluir com consistência")
proxima_prova = get_next_race(provas_salvas)
zonas_ritmo = compute_pace_zones(perfil, provas_salvas)

nome_seguro = esc(usuario_input.capitalize())
esporte_seguro = esc(esporte_atual)
objetivo_seguro = esc(objetivo_atual)

if proxima_prova:
    dias_f = proxima_prova["dias_restantes"]
    fase_nome, fase_desc = get_periodization_phase(dias_f)
    prova_nome_seguro = esc(proxima_prova["nome"])
    prova_mod_seguro = esc(proxima_prova["modalidade"])

    texto_dias = "É hoje! Boa prova!" if dias_f == 0 else (
        "Falta 1 dia para a prova" if dias_f == 1 else f"Faltam {dias_f} dias para {prova_nome_seguro}"
    )
    subtitulo_topo = f"{texto_dias} ({prova_mod_seguro}) • {esc(fase_desc)}"
    pill_html = f'<div class="pill-fase">Semana {semana_num} • {esc(fase_nome)} • {APP_VERSION}</div>'
else:
    subtitulo_topo = f"{esporte_seguro} • Foco: {objetivo_seguro}"
    pill_html = f'<div class="pill-fase">Semana {semana_num} de treino • {APP_VERSION}</div>'

st.markdown(f"""
<div class="welcome-card">
    <div class="welcome-title">{greeting_br()}, {nome_seguro}! 👋</div>
    <div class="welcome-sub">{subtitulo_topo}</div>
    {pill_html}
</div>
""", unsafe_allow_html=True)

feedback_semana_atual = dados_atleta.get("feedback_semana", "")
if feedback_semana_atual:
    st.markdown(f"""
    <div class="coach-note">
        <div class="coach-note-title">💬 Avaliação do Treinador sobre a semana anterior</div>
        {esc(feedback_semana_atual)}
    </div>
    """, unsafe_allow_html=True)

if zonas_ritmo:
    st.markdown(f"""
    <div class="zones-bar">
        <strong>🎯 Suas Zonas de Ritmo</strong> <em>({esc(zonas_ritmo['fonte'])})</em>:<br>
        <strong>Z1:</strong> {esc(zonas_ritmo['Z1 (Regenerativo)'])} &nbsp;|&nbsp;
        <strong>Z2:</strong> {esc(zonas_ritmo['Z2 (Base Aeróbica)'])} &nbsp;|&nbsp;
        <strong>Z3:</strong> {esc(zonas_ritmo['Z3 (Ritmo / Tempo)'])} &nbsp;|&nbsp;
        <strong>Z4:</strong> {esc(zonas_ritmo['Z4 (Limiar)'])} &nbsp;|&nbsp;
        <strong>Z5:</strong> {esc(zonas_ritmo['Z5 (Tiros / VO2)'])}
    </div>
    """, unsafe_allow_html=True)

planilha_atual = dados_atleta.get("planilha", [])

# ==========================================
# FLUXO INICIAL (SEM PLANILHA ATIVA)
# ==========================================
if not planilha_atual:
    aba_criar, aba_importar = st.tabs(["✨ Montar meu plano", "📥 Já tenho uma planilha"])

    with aba_criar:
        col1, col2 = st.columns(2)
        with col1:
            esporte = st.selectbox("O que você vai treinar?", MODALIDADES)
            nivel = st.selectbox("Como está seu ritmo hoje?", ["Iniciante", "Intermediário", "Avançado"])
        with col2:
            objetivo = st.text_input(
                "Qual é o seu objetivo?",
                max_chars=140,
                placeholder="Ex: Completar meus primeiros 5 km / Triathlon SuperSprint"
            )
            observacoes = st.text_area(
                "Algo que eu precise saber sobre você?",
                max_chars=400,
                placeholder="Ex: Tenho 45 min por dia, prefiro treinar de manhã...",
                height=100
            )

        st.markdown("**Vai fazer alguma prova em breve? (Opcional)**")
        c_p1, c_p2, c_p3 = st.columns([2, 1.5, 1.2])
        with c_p1:
            prova_init_nome = st.text_input("Nome da prova", max_chars=80, placeholder="Ex: Corrida da Cidade 5km", key="p_init_nome")
        with c_p2:
            prova_init_mod = st.text_input("Distância / Modalidade", max_chars=50, placeholder="Ex: 5 km ou SuperSprint", key="p_init_mod")
        with c_p3:
            prova_init_data = st.date_input("Data da prova", value=today_br() + timedelta(days=45), min_value=today_br(), key="p_init_data")

        if st.button("Montar minha primeira semana", type="primary", use_container_width=True):
            if not dias_selecionados:
                st.error("Escolha pelo menos 1 dia na barra lateral para treinar.")
            else:
                with st.spinner("Preparando seus treinos..."):
                    try:
                        provas_iniciais = []
                        if prova_init_nome.strip():
                            provas_iniciais.append({
                                "nome": prova_init_nome.strip()[:80],
                                "modalidade": (prova_init_mod.strip() or esporte)[:50],
                                "data": prova_init_data.isoformat(),
                                "tempo_prova": "",
                                "eh_pr": False
                            })

                        dias_descanso = [d for d in DIAS_SEMANA if d not in dias_selecionados]
                        info_provas = build_races_context(provas_iniciais, zonas_ritmo)
                        obj_clean = sanitize_prompt_input(objetivo or "Evoluir com saúde e consistência", 140)
                        obs_clean = sanitize_prompt_input(observacoes or "Nenhuma", 400)

                        prompt = f"""
Monte os treinos da Semana 1 para este aluno:
<dados_aluno>
- Esporte principal: {esporte}
- Nível atual: {nivel}
- Objetivo: {obj_clean}
- Dias disponíveis para treinar: {', '.join(dias_selecionados)}
- Dias de descanso: {', '.join(dias_descanso) if dias_descanso else 'Nenhum'}
- Observações pessoais: {obs_clean}
</dados_aluno>

<calendario_provas_e_zonas>
{info_provas}
</calendario_provas_e_zonas>

REGRAS:
1. Retorne os 7 dias da semana na ordem exata: Segunda, Terça, Quarta, Quinta, Sexta, Sábado, Domingo.
2. Coloque treino APENAS nos dias disponíveis ({', '.join(dias_selecionados)}). Nos outros dias, use "modalidade": "Descanso" e "titulo": "Dia de descanso".
3. Se houver zonas de ritmo calculadas acima, inclua os ritmos alvo nas sessões de corrida.
4. Retorne um array JSON com 7 objetos contendo as chaves: "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist".
"""
                        resposta = request_plan_json(prompt)
                        nova_planilha = parse_and_validate_week(resposta)
                        dados_atleta["perfil"] = {
                            "esporte": esporte,
                            "nivel": nivel,
                            "objetivo": obj_clean,
                            "dias_disponiveis": dias_selecionados,
                            "observacoes": obs_clean,
                            "tempo_5k": perfil.get("tempo_5k", "")
                        }
                        dados_atleta["provas"] = provas_iniciais
                        dados_atleta["semana_atual"] = 1
                        dados_atleta["feedback_semana"] = ""
                        dados_atleta["planilha"] = nova_planilha
                        save_athlete(usuario_input, dados_atleta)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Não foi possível montar o plano agora: {exc}")

    with aba_importar:
        st.write("Cole o texto da planilha que você já segue para organizar aqui:")
        texto_importado = st.text_area(
            "Sua planilha atual:",
            max_chars=2500,
            height=180,
            placeholder="Segunda: Corrida leve 5km\nQuarta: Tiros 6x400m..."
        )
        esporte_imp = st.text_input("Qual é o esporte principal?", max_chars=50, value="Corrida")

        if st.button("Organizar minha planilha", type="primary", use_container_width=True):
            if not texto_importado.strip():
                st.error("Cole o texto da planilha primeiro.")
            else:
                with st.spinner("Organizando seus treinos..."):
                    try:
                        planilha_clean = sanitize_prompt_input(texto_importado, 2500)
                        prompt = f"""
Organize a planilha abaixo nos 7 dias da semana (Segunda a Domingo).
<planilha_usuario>
{planilha_clean}
</planilha_usuario>

Retorne um array JSON com 7 objetos (Segunda a Domingo) e as chaves:
"dia", "modalidade", "titulo", "descricao", "duracao_ou_dist"
"""
                        resposta = request_plan_json(prompt)
                        nova_planilha = parse_and_validate_week(resposta)
                        dados_atleta["perfil"] = {
                            "esporte": sanitize_prompt_input(esporte_imp, 50) or "Corrida",
                            "nivel": "Intermediário",
                            "objetivo": "Evolução contínua",
                            "dias_disponiveis": dias_selecionados,
                            "tempo_5k": perfil.get("tempo_5k", "")
                        }
                        dados_atleta["semana_atual"] = 1
                        dados_atleta["feedback_semana"] = ""
                        dados_atleta["planilha"] = nova_planilha
                        save_athlete(usuario_input, dados_atleta)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Não foi possível importar essa planilha: {exc}")

# ==========================================
# PAINEL PRINCIPAL (PLANILHA ATIVA)
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
    # ABA 1: TREINOS DA SEMANA
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
                    if item.get("analise_arquivo"):
                        st.info(f"💬 **Análise do Treinador:** {item['analise_arquivo']}")

                if not eh_descanso:
                    st.divider()
                    c1, c2 = st.columns([1, 1.5])
                    with c1:
                        k_conc = f"conc_{semana_num}_{i}"
                        st.checkbox(
                            "Já fiz esse treino",
                            value=item.get("concluido", False),
                            key=k_conc,
                            on_change=persist_workout_field,
                            args=(i, "concluido", k_conc)
                        )

                    with c2:
                        k_sens = f"sens_{semana_num}_{i}"
                        idx_sens = (
                            SENSACOES.index(item.get("sensacao", "Ainda não fiz"))
                            if item.get("sensacao") in SENSACOES else 0
                        )
                        st.selectbox(
                            "Como você se sentiu?",
                            options=SENSACOES,
                            index=idx_sens,
                            key=k_sens,
                            on_change=persist_workout_field,
                            args=(i, "sensacao", k_sens)
                        )

                    k_fb = f"fb_{semana_num}_{i}"
                    st.text_input(
                        "Anotações sobre o treino (opcional)",
                        value=item.get("feedback", ""),
                        max_chars=500,
                        placeholder="Ex: Consegui manter o ritmo no final, me senti bem...",
                        key=k_fb,
                        on_change=persist_workout_field,
                        args=(i, "feedback", k_fb)
                    )

                    arquivo_up = st.file_uploader(
                        "Enviar arquivo do Garmin ou Strava (.fit, .tcx, .gpx)",
                        type=["fit", "tcx", "gpx"],
                        key=f"up_{semana_num}_{i}"
                    )
                    if arquivo_up is not None:
                        try:
                            resumo_arq, arq_hash = parse_activity_file(arquivo_up)
                            if planilha_atual[i].get("arquivo_hash") != arq_hash:
                                with st.spinner("Lendo atividade e avaliando desempenho..."):
                                    analise_arq = evaluate_uploaded_activity(planilha_atual[i], resumo_arq)
                                    planilha_atual[i]["dados_arquivo"] = resumo_arq
                                    planilha_atual[i]["analise_arquivo"] = analise_arq[:600]
                                    planilha_atual[i]["arquivo_hash"] = arq_hash
                                    planilha_atual[i]["concluido"] = True
                                    if planilha_atual[i]["sensacao"] == "Ainda não fiz":
                                        planilha_atual[i]["sensacao"] = "Na medida certa"
                                    dados_atleta["planilha"] = planilha_atual
                                    save_athlete(usuario_input, dados_atleta)
                                    st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível ler esse arquivo: {exc}")

        st.write("")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("💾 Salvar anotações", use_container_width=True):
                dados_atleta["planilha"] = planilha_atual
                save_athlete(usuario_input, dados_atleta)
                st.success("Tudo salvo!")

        with col_b2:
            if st.button("Fechar semana e montar a próxima ➡️", type="primary", use_container_width=True):
                if not dias_selecionados:
                    st.error("Escolha pelo menos 1 dia de treino na barra lateral.")
                else:
                    with st.spinner("Avaliando sua semana e preparando a próxima..."):
                        try:
                            dias_descanso = [d for d in DIAS_SEMANA if d not in dias_selecionados]
                            info_provas = build_races_context(provas_salvas, zonas_ritmo)
                            resumo_semana = json.dumps(planilha_atual, ensure_ascii=False)

                            prompt = f"""
Analise como foi a Semana {semana_num} deste aluno e monte os treinos da Semana {semana_num + 1}.

<perfil_aluno>
{json.dumps(dados_atleta.get('perfil', {}), ensure_ascii=False)}
</perfil_aluno>

<calendario_provas_e_zonas>
{info_provas}
</calendario_provas_e_zonas>

Dias disponíveis para treinar na Semana {semana_num + 1}: {', '.join(dias_selecionados)}
Dias de descanso: {', '.join(dias_descanso) if dias_descanso else 'Nenhum'}

<execucao_semana_{semana_num}>
{resumo_semana}
</execucao_semana_{semana_num}>

REGRAS DE PERIODIZAÇÃO:
- Respeite a fase da prova (Base, Construção, Pico ou Polimento na semana da prova).
- Use os tempos, PRs e zonas de ritmo calculadas como referência de pace.
- Se o aluno completou bem e se sentiu leve/na medida, evolua gradualmente.
- Se relatou cansaço, treino pesado/exausto ou faltou a treinos, reduza a carga para recuperação.
- Coloque treinos APENAS nos dias selecionados ({', '.join(dias_selecionados)}). Nos outros dias, coloque "modalidade": "Descanso".

FORMATO DE RESPOSTA:
Retorne EXCLUSIVAMENTE um objeto JSON com duas chaves:
1. "feedback_semana": Um comentário curto, humano e direto (2 a 3 frases) avaliando como o aluno foi na Semana {semana_num} e o foco da Semana {semana_num + 1}.
2. "planilha": Um array com os 7 objetos da semana (Segunda a Domingo) e as chaves: "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist".
"""
                            resposta = request_plan_json(prompt)
                            feedback_gerado, proxima_planilha = parse_next_week_with_feedback(resposta)

                            historico = dados_atleta.get("historico", [])
                            historico.append({
                                "semana": semana_num,
                                "data_fechamento": today_br().strftime("%d/%m/%Y"),
                                "adesao": taxa_adesao,
                                "treinos_concluidos": len(concluidos),
                                "treinos_totais": len(treinos_ativos),
                                "feedback_treinador": feedback_gerado,
                                "planilha": json.loads(json.dumps(planilha_atual))
                            })

                            dados_atleta["historico"] = historico
                            dados_atleta["semana_atual"] = semana_num + 1
                            dados_atleta["feedback_semana"] = feedback_gerado
                            dados_atleta["planilha"] = proxima_planilha
                            save_athlete(usuario_input, dados_atleta)
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível gerar a próxima semana: {exc}")

    # ------------------------------------------
    # ABA 2: MINHAS PROVAS
    # ------------------------------------------
    with tab_provas:
        st.subheader("🏆 Suas Provas Alvo")
        st.write("Cadastre provas futuras para guiar seus treinos, ou provas já realizadas para registrar seu tempo oficial e PR.")

        with st.form("form_nova_prova", clear_on_submit=True):
            cp1, cp2, cp3 = st.columns([2, 1.5, 1.2])
            with cp1:
                nova_prova_nome = st.text_input("Nome da prova", max_chars=80, placeholder="Ex: Meia Maratona de Vitória")
            with cp2:
                nova_prova_mod = st.text_input("Modalidade / Distância", max_chars=50, placeholder="Ex: Corrida 21 km / Triathlon")
            with cp3:
                nova_prova_data = st.date_input("Data", value=today_br() + timedelta(days=30))

            if st.form_submit_button("Adicionar ao calendário", type="primary"):
                if not nova_prova_nome.strip():
                    st.warning("Coloque o nome da prova antes de salvar.")
                else:
                    provas_salvas.append({
                        "nome": nova_prova_nome.strip()[:80],
                        "modalidade": (nova_prova_mod.strip() or esporte_atual)[:50],
                        "data": nova_prova_data.isoformat(),
                        "tempo_prova": "",
                        "eh_pr": False
                    })
                    dados_atleta["provas"] = provas_salvas
                    save_athlete(usuario_input, dados_atleta)
                    st.success("Prova adicionada ao calendário!")
                    st.rerun()

        st.divider()
        if provas_salvas:
            today = today_br()
            provas_ordenadas = sorted(provas_salvas, key=lambda x: x.get("data", ""))

            for idx_p, p in enumerate(provas_ordenadas):
                try:
                    dt_p = date.fromisoformat(p["data"])
                    dias_rest = (dt_p - today).days
                    data_fmt = dt_p.strftime("%d/%m/%Y")
                except Exception:
                    dias_rest = 0
                    data_fmt = p.get("data", "")

                if dias_rest >= 0:
                    col_info, col_del = st.columns([4, 1])
                    with col_info:
                        fase_p, desc_p = get_periodization_phase(dias_rest)
                        contagem = "É hoje! Boa prova!" if dias_rest == 0 else (
                            "Falta 1 dia" if dias_rest == 1 else f"Faltam {dias_rest} dias"
                        )
                        st.markdown(
                            f"🎯 **{p['nome']}** ({p['modalidade']}) — 📅 {data_fmt}  \n"
                            f"⏳ **{contagem}** • *{fase_p}:* {desc_p}"
                        )
                    with col_del:
                        if st.button("Remover", key=f"del_prova_{idx_p}", use_container_width=True):
                            provas_salvas.remove(p)
                            dados_atleta["provas"] = provas_salvas
                            save_athlete(usuario_input, dados_atleta)
                            st.rerun()
                else:
                    col_info, col_del = st.columns([4, 1])
                    with col_info:
                        badge_pr = " • 🏆 **PR (Recorde Pessoal)!**" if p.get("eh_pr") else ""
                        tempo_atual_txt = f" • ⏱️ Tempo: **{p['tempo_prova']}**" if p.get("tempo_prova") else ""
                        st.markdown(
                            f"✅ **{p['nome']}** ({p['modalidade']}) — 📅 {data_fmt} *(Prova já realizada)*{tempo_atual_txt}{badge_pr}"
                        )
                    with col_del:
                        if st.button("Remover", key=f"del_prova_{idx_p}", use_container_width=True):
                            provas_salvas.remove(p)
                            dados_atleta["provas"] = provas_salvas
                            save_athlete(usuario_input, dados_atleta)
                            st.rerun()

                    with st.expander("⏱️ Registrar / editar tempo de prova e PR", expanded=not bool(p.get("tempo_prova"))):
                        ct1, ct2, ct3 = st.columns([2, 1.3, 1])
                        with ct1:
                            novo_tempo = st.text_input(
                                "Seu tempo oficial",
                                value=p.get("tempo_prova", ""),
                                max_chars=30,
                                placeholder="Ex: 00:24:35 ou 1h48min",
                                key=f"tempo_prova_{idx_p}"
                            )
                        with ct2:
                            st.write("")
                            st.write("")
                            novo_pr = st.checkbox(
                                "🏆 Foi meu PR!",
                                value=bool(p.get("eh_pr", False)),
                                key=f"pr_prova_{idx_p}"
                            )
                        with ct3:
                            st.write("")
                            st.write("")
                            if st.button("Salvar resultado", key=f"save_res_{idx_p}", type="primary", use_container_width=True):
                                p["tempo_prova"] = novo_tempo.strip()[:30]
                                p["eh_pr"] = novo_pr
                                dados_atleta["provas"] = provas_salvas
                                save_athlete(usuario_input, dados_atleta)
                                st.success("Resultado salvo!")
                                st.rerun()

                st.divider()
        else:
            st.info("Você ainda não marcou nenhuma prova. Cadastre uma acima para ativar a preparação específica!")

    # ------------------------------------------
    # ABA 3: FALAR COM TREINADOR
    # ------------------------------------------
    with tab_chat:
        st.subheader("💬 Precisa adaptar algum treino?")
        st.write("Mudou seu horário, choveu ou bateu um cansaço extra? Me conta o que houve que eu reorganizo a semana para você.")

        pedido_ajuste = st.text_area(
            "O que você gostaria de mudar?",
            max_chars=500,
            placeholder="Ex: Hoje não deu tempo de correr, joga esse treino para amanhã.\nEx: Senti a panturrilha pesada, deixa o próximo treino bem leve.",
            height=110
        )

        if st.button("Adaptar meus treinos", type="primary"):
            if not pedido_ajuste.strip():
                st.warning("Me diga o que você precisa mudar primeiro.")
            else:
                with st.spinner("Reorganizando sua semana..."):
                    try:
                        pedido_clean = sanitize_prompt_input(pedido_ajuste, 500)
                        prompt_ajuste = f"""
O aluno pediu uma adaptação na Semana {semana_num}.

<treinos_atuais>
{json.dumps(planilha_atual, ensure_ascii=False)}
</treinos_atuais>

<calendario_provas_e_zonas>
{build_races_context(provas_salvas, zonas_ritmo)}
</calendario_provas_e_zonas>

<pedido_aluno>
{pedido_clean}
</pedido_aluno>

REGRAS:
1. Ajuste APENAS os dias necessários para atender o pedido dentro de <pedido_aluno>, mantendo intactos os treinos já concluídos ("concluido", "sensacao", "feedback", "dados_arquivo", "analise_arquivo", "arquivo_hash").
2. Mantenha os 7 dias da semana (Segunda a Domingo).
3. Retorne um array JSON atualizado com 7 objetos e as chaves: "dia", "modalidade", "titulo", "descricao", "duracao_ou_dist", "concluido", "sensacao", "feedback", "dados_arquivo", "analise_arquivo", "arquivo_hash".
"""
                        resposta = request_plan_json(prompt_ajuste)
                        planilha_ajustada = parse_and_validate_week(resposta)
                        dados_atleta["planilha"] = planilha_ajustada
                        save_athlete(usuario_input, dados_atleta)
                        st.success("Pronto! Já atualizei seus treinos.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Não foi possível fazer o ajuste agora: {exc}")

    # ------------------------------------------
    # ABA 4: SEMANAS ANTERIORES
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

            if registro_semana.get("feedback_treinador"):
                st.info(f"💬 **Avaliação do Treinador:** {registro_semana['feedback_treinador']}")

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
    # ABA 5: EXPORTAR (WHATSAPP, PDF & AGENDA)
    # ------------------------------------------
    with tab_exportar:
        st.subheader("📤 Levar treinos para o celular")
        col_ex1, col_ex2 = st.columns(2)

        with col_ex1:
            st.markdown("**Copiar para o WhatsApp**")
            texto_wpp = format_whatsapp_plan(usuario_input, semana_num, planilha_atual)
            st.text_area("Texto formatado:", value=texto_wpp, height=240)

        with col_ex2:
            st.markdown("**Baixar em PDF ou Adicionar ao Calendário**")
            st.write("Exporte sua planilha da semana em PDF ou importe direto na sua agenda.")

            pdf_bytes = build_plan_pdf(usuario_input, semana_num, perfil, planilha_atual, feedback_semana_atual)
            st.download_button(
                label="📄 Baixar Planilha em PDF",
                data=pdf_bytes,
                file_name=f"treinos_semana_{semana_num}_{usuario_input}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )

            st.write("")
            ics_conteudo = build_ics_calendar(usuario_input, semana_num, planilha_atual)
            st.download_button(
                label="📅 Baixar para minha Agenda (.ics)",
                data=ics_conteudo,
                file_name=f"treinos_semana_{semana_num}_{usuario_input}.ics",
                mime="text/calendar",
                use_container_width=True
            )
