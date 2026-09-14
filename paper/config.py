import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_ROOT = os.path.join(BASE_DIR, "state")
os.makedirs(STATE_ROOT, exist_ok=True)

PROFILES = ("baseline", "wave3", "copytrader")

INITIAL_CAPITAL = 10_000.0
EXPERIMENT_DAYS = 30

UNIVERSE_TOP_N = 60
CANDIDATE_POOL = 250
MIN_ADV_USD = 5_000_000
MIN_HISTORY_DAYS = 60
ADV_WINDOW = 30

LOOKBACKS = (14, 21, 30, 45, 60)
K_PER_SIDE = 10
VOL_WINDOW = 30
KLINES_LIMIT = 260
REGIME_MA = 200
REGIME_SOFT = 0.5
FUNDING_SIGNAL_DAYS = 30

FEE_BPS = 5.0
SLIP_BPS = 2.0
MIN_ORDER_USD = 10.0

VOL_TARGET_ANNUAL = 0.45
PER_NAME_CAP = 0.10
DD_BREAKER_RESUME = 0.05
DD_BREAKER_GROSS_SCALE = 0.5
BLOCK_NEW_SHORTS_ON_BREACH = False
FUNDING_CAP = 0.0075

RM_LOOKBACK = 90
RM_TARGET_VOL = 0.20
RM_MAX_SCALE = 2.0

BASE_URL = "https://fapi.binance.com"

PROFILE_CFG = {
    "baseline": {
        "label": "Baseline (ensemble momentum)",
        "strategy": "XS_MOMENTUM_ENSEMBLE",
        "kind": "strategy",
        "funding_tilt": False,
        "regime": False,
        "risk_managed": False,
        "vol_target": VOL_TARGET_ANNUAL,
        "dd_breaker_trigger": 0.15,
    },
    "wave3": {
        "label": "Wave3 (momentum - funding tilt, soft BTC regime, risk-managed)",
        "strategy": "XS_MOMENTUM_FUNDING_REGIME_RM",
        "kind": "strategy",
        "funding_tilt": True,
        "regime": True,
        "risk_managed": True,
        "vol_target": None,
        "dd_breaker_trigger": 0.20,
    },
    "copytrader": {
        "label": "Copy-trader simulation (lead-trader log replay)",
        "strategy": "COPY_SIMULATION",
        "kind": "copy_sim",
        "funding_tilt": False,
        "regime": False,
        "risk_managed": False,
        "vol_target": None,
        "dd_breaker_trigger": 0.20,
    },
}


def profile_dir(profile):
    d = os.path.join(STATE_ROOT, profile)
    os.makedirs(d, exist_ok=True)
    return d


def files(profile):
    d = profile_dir(profile)
    return {
        "account": os.path.join(d, "account.json"),
        "trades": os.path.join(d, "trades.csv"),
        "daily": os.path.join(d, "daily.csv"),
        "targets": os.path.join(d, "targets.csv"),
        "events": os.path.join(d, "events.csv"),
    }


def cfg_for(profile):
    if profile not in PROFILE_CFG:
        raise ValueError(f"unknown profile {profile!r}; expected one of {PROFILES}")
    return PROFILE_CFG[profile]
