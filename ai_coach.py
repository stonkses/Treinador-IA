import json
import re
import streamlit as st
from google import genai
from google.genai import types
from config import DIAS_SEMANA_ORDEM
from database import normalizar_item_treino

@st.cache_resource
def get_gemini_client() -> genai.Client:
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        raise ValueError("Chave GEMINI_API_KEY não encontrada nas configurações.")
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})

@st.cache_data(ttl=3600, show_spinner=False)
def listar_modelos_candidatos() -> list[str]:
    preferidos = [
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.1-pro-preview",
    ]
    try:
        client = get_gemini_client()
        disponiveis = []
        for m in client.models.list():
            nome = m.name.replace("models/", "")
            if "gemini" in nome and "embedding" not in nome and "imagen" not in nome:
                disponiveis.append(nome)
        candidatos = [m for m in preferidos if m in disponiveis] + [
            m for m in disponiveis if m not in preferidos
        ]
        return candidatos if candidatos else preferidos
    except Exception:
        return preferidos

def gerar_json_ia(prompt: str) -> str:
    client = get_gemini_client()
    candidatos = listar_modelos_candidatos()

    erros = []
    for modelo in candidatos[:5]:
        try:
            response = client.models.generate_content(
                model=modelo,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.4
                )
            )
            return response.text
        except Exception as e:
            erros.append(f"{modelo}: {e}")
            continue
    raise RuntimeError(" | ".join(erros))

def validar_e_normalizar_semana(lista_bruta: list) -> list:
    mapa_dias = {}
    for item in lista_bruta:
        if not isinstance(item, dict):
            continue
        item_norm = normalizar_item_treino(item)
        dia_str = item_norm["dia"].strip().lower()
        for dia_oficial in DIAS_SEMANA_ORDEM:
            if dia_oficial.lower() in dia_str and dia_oficial not in mapa_dias:
                item_norm["dia"] = dia_oficial
                mapa_dias[dia_oficial] = item_norm
                break

    semana_validada = []
    for dia_oficial in DIAS_SEMANA_ORDEM:
        if dia_oficial in mapa_dias:
            semana_validada.append(mapa_dias[dia_oficial])
        else:
            semana_validada.append(normalizar_item_treino({
                "dia": dia_oficial,
                "modalidade": "Descanso",
                "titulo": "Dia de descanso",
                "descricao": "Recuperação ativa e descanso.",
                "duracao_ou_dist": "-"
            }))
    return semana_validada

def extrair_e_validar_planilha(texto: str) -> list:
    texto_limpo = re.sub(r"```json\s*", "", texto, flags=re.IGNORECASE)
    texto_limpo = re.sub(r"```\s*", "", texto_limpo).strip()
    inicio = texto_limpo.find("[")
    fim = texto_limpo.rfind("]")
    if inicio != -1 and fim != -1:
        texto_limpo = texto_limpo[inicio:fim + 1]
    dados = json.loads(texto_limpo)
    if isinstance(dados, dict):
        for v in dados.values():
            if isinstance(v, list):
                dados = v
                break
    if not isinstance(dados, list):
        raise ValueError("A resposta da IA não retornou uma lista de treinos válida.")
    return validar_e_normalizar_semana(dados)
