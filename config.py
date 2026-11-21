from zoneinfo import ZoneInfo

APP_VERSION = "v3.0"
TZ_BR = ZoneInfo("America/Sao_Paulo")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 300

DIAS_SEMANA = [
    "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"
]

SENSACOES = [
    "Ainda não fiz",
    "Leve e tranquilo",
    "Na medida certa",
    "Pesado, mas deu",
    "Exausto / Muito difícil"
]

MODALIDADES = [
    "Corrida de Rua",
    "Triathlon",
    "Musculação / Hipertrofia",
    "Ciclismo",
    "Natação",
    "CrossFit / Funcional",
    "Híbrido (Corrida + Musculação)"
]

APP_CSS = """
<style>
    #MainMenu, footer {visibility: hidden;}
    header {background: transparent !important;}

    .stApp {
        background-color: #0F141E;
        color: #E2E8F0;
    }

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

    div[data-testid="stExpander"] {
        background-color: #161D2C !important;
        border: 1px solid #253046 !important;
        border-radius: 16px !important;
        margin-bottom: 12px !important;
        transition: border-color 0.2s ease;
    }
    div[data-testid="stExpander"]:hover {
        border-color: #475569 !important;
    }

    button[data-baseweb="tab"] {
        font-weight: 500 !important;
        font-size: 0.95rem !important;
        padding: 10px 16px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #FB923C !important;
        font-weight: 600 !important;
    }

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
"""
