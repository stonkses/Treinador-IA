import hashlib
import hmac
import streamlit as st
from supabase import create_client, Client
from config import SENSACOES_OPCOES

@st.cache_resource
def get_supabase_client() -> Client | None:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

def gerar_hash_pin(usuario: str, pin: str) -> str:
    sal = f"treinador-ia:{usuario.strip().lower()}"
    return hashlib.sha256(f"{sal}:{pin.strip()}".encode("utf-8")).hexdigest()

def verificar_pin(usuario: str, pin_digitado: str, hash_salvo: str) -> bool:
    if not hash_salvo:
        return True
    hash_tentativa = gerar_hash_pin(usuario, pin_digitado)
    return hmac.compare_digest(hash_tentativa, hash_salvo)

def estrutura_padrao(pin_hash: str = "") -> dict:
    return {
        "pin_hash": pin_hash,
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
        "sensacao": sensacao_salva if sensacao_salva in SENSACOES_OPCOES else "Ainda não fiz",
        "feedback": str(item.get("feedback", "")),
        "dados_arquivo": str(item.get("dados_arquivo", "")),
        "arquivo_hash": str(item.get("arquivo_hash", ""))
    }

def buscar_registro_bruto(usuario: str) -> dict | None:
    sb = get_supabase_client()
    if not sb:
        return None
    try:
        resp = sb.table("atletas").select("dados").eq("usuario", usuario).execute()
        if resp.data and len(resp.data) > 0:
            dados = resp.data[0].get("dados") or {}
            base = estrutura_padrao()
            base.update(dados)
            if base.get("planilha"):
                base["planilha"] = [normalizar_item_treino(t) for t in base["planilha"]]
            if not base.get("provas"):
                base["provas"] = []
            return base
    except Exception as e:
        st.error(f"Não consegui consultar os dados no servidor: {e}")
    return None

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
