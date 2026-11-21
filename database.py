import hashlib
import hmac
import re
import time
import streamlit as st
from supabase import create_client, Client
from config import SENSACOES, MAX_LOGIN_ATTEMPTS, LOCKOUT_SECONDS

USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]{2,24}$")


@st.cache_resource
def get_db() -> Client | None:
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except Exception:
        return None


def validar_username(raw: str) -> str | None:
    limpo = raw.strip().lower()
    if USERNAME_PATTERN.match(limpo):
        return limpo
    return None


def hash_pin(usuario: str, pin: str) -> str:
    salt = f"treinador-v3:{usuario.strip().lower()}"
    return hashlib.pbkdf2_hmac(
        "sha256",
        pin.strip().encode("utf-8"),
        salt.encode("utf-8"),
        120_000
    ).hex()


def _hash_pin_legado(usuario: str, pin: str) -> str:
    sal = f"treinador-ia:{usuario.strip().lower()}"
    return hashlib.sha256(f"{sal}:{pin.strip()}".encode("utf-8")).hexdigest()


def verificar_pin(usuario: str, pin_digitado: str, stored_hash: str) -> tuple[bool, bool]:
    """Retorna (valido, precisa_migrar_hash)."""
    if not stored_hash:
        return True, False

    novo_tentativa = hash_pin(usuario, pin_digitado)
    if hmac.compare_digest(novo_tentativa, stored_hash):
        return True, False

    if len(stored_hash) == 64:
        legado_tentativa = _hash_pin_legado(usuario, pin_digitado)
        if hmac.compare_digest(legado_tentativa, stored_hash):
            return True, True

    return False, False


def checar_bloqueio_login(usuario: str) -> int:
    """Retorna segundos restantes de bloqueio (0 se liberado)."""
    tentativas = st.session_state.setdefault("login_guard", {})
    info = tentativas.get(usuario)
    if not info:
        return 0
    restante = int(info.get("locked_until", 0) - time.time())
    if restante > 0:
        return restante
    tentativas.pop(usuario, None)
    return 0


def registrar_falha_login(usuario: str) -> int:
    tentativas = st.session_state.setdefault("login_guard", {})
    info = tentativas.get(usuario, {"count": 0, "locked_until": 0})
    info["count"] += 1
    if info["count"] >= MAX_LOGIN_ATTEMPTS:
        info["locked_until"] = time.time() + LOCKOUT_SECONDS
        info["count"] = 0
    tentativas[usuario] = info
    return max(0, MAX_LOGIN_ATTEMPTS - info["count"])


def limpar_falhas_login(usuario: str):
    tentativas = st.session_state.get("login_guard", {})
    tentativas.pop(usuario, None)


def default_athlete_data(pin_hash: str = "") -> dict:
    return {
        "pin_hash": pin_hash,
        "perfil": {},
        "semana_atual": 1,
        "planilha": [],
        "historico": [],
        "provas": []
    }


def _to_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "sim", "yes", "s", "concluido", "concluído")
    return bool(val)


def normalize_workout(item: dict) -> dict:
    sensacao = str(item.get("sensacao", ""))
    if not sensacao and item.get("rpe_real"):
        rpe = int(item.get("rpe_real", 0))
        if rpe <= 4:
            sensacao = "Leve e tranquilo"
        elif rpe <= 7:
            sensacao = "Na medida certa"
        elif rpe <= 9:
            sensacao = "Pesado, mas deu"
        else:
            sensacao = "Exausto / Muito difícil"

    return {
        "dia": str(item.get("dia", "Dia"))[:30],
        "modalidade": str(item.get("modalidade") or item.get("esporte") or item.get("tipo") or "Treino")[:60],
        "titulo": str(item.get("titulo") or item.get("treino") or item.get("foco") or "Sessão")[:120],
        "descricao": str(item.get("descricao") or item.get("detalhes") or item.get("prescricao") or "")[:2000],
        "duracao_ou_dist": str(item.get("duracao_ou_dist") or item.get("volume") or item.get("duracao") or "-")[:60],
        "concluido": _to_bool(item.get("concluido", False)),
        "sensacao": sensacao if sensacao in SENSACOES else "Ainda não fiz",
        "feedback": str(item.get("feedback", ""))[:600],
        "dados_arquivo": str(item.get("dados_arquivo", ""))[:300],
        "arquivo_hash": str(item.get("arquivo_hash", ""))[:32]
    }


def fetch_athlete(usuario: str) -> dict | None:
    db = get_db()
    if not db:
        return None
    try:
        res = db.table("atletas").select("dados").eq("usuario", usuario).limit(1).execute()
        if res.data:
            raw = res.data[0].get("dados") or {}
            base = default_athlete_data()
            base.update(raw)
            if base.get("planilha"):
                base["planilha"] = [normalize_workout(t) for t in base["planilha"]]
            if not isinstance(base.get("provas"), list):
                base["provas"] = []
            return base
    except Exception as exc:
        st.error(f"Erro ao conectar ao banco de dados: {exc}")
    return None


def save_athlete(usuario: str, dados: dict):
    db = get_db()
    if not db:
        return
    try:
        db.table("atletas").upsert({
            "usuario": usuario,
            "dados": dados
        }).execute()
    except Exception as exc:
        st.error(f"Falha ao salvar alterações: {exc}")
