import logging
import os
import pickle
import time
from functools import partial
from multiprocessing.pool import ThreadPool

import pandas as pd
import requests
import tqdm
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import ace_lib as ace

# ── Patch missing attributes so ace_extensions works with this ace_lib ────────

# Base API URL
if not hasattr(ace, 'brain_api_url'):
    ace.brain_api_url = "https://api.worldquantbrain.com"

# Logger
if not hasattr(ace, 'logger'):
    ace.logger = logging.getLogger("ace_lib")
    logging.basicConfig(level=logging.INFO)

# SingleSession — plain requests.Session (retry adapter added in get_stored_session)
if not hasattr(ace, 'SingleSession'):
    ace.SingleSession = requests.Session

# check_session_and_relogin — re-login when session nears expiry
if not hasattr(ace, 'check_session_and_relogin'):
    def _check_session_and_relogin(s):
        if ace.check_session_timeout(s) < 1000:
            return ace.start_session()
        return s
    ace.check_session_and_relogin = _check_session_and_relogin

# ─────────────────────────────────────────────────────────────────────────────


def get_stored_session(duration=1800):
    # Map BRAIN_CREDENTIAL_* (from .env) → ACE_CREDENTIAL_* (expected by ace_lib)
    if os.getenv('BRAIN_CREDENTIAL_EMAIL') and not os.getenv('ACE_CREDENTIAL_EMAIL'):
        os.environ['ACE_CREDENTIAL_EMAIL'] = os.getenv('BRAIN_CREDENTIAL_EMAIL', '').strip()
    if os.getenv('BRAIN_CREDENTIAL_PASSWORD') and not os.getenv('ACE_CREDENTIAL_PASSWORD'):
        os.environ['ACE_CREDENTIAL_PASSWORD'] = os.getenv('BRAIN_CREDENTIAL_PASSWORD', '').strip()

    brain_session = requests.Session()

    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    brain_session.mount("https://", adapter)
    brain_session.mount("http://", adapter)

    if os.path.exists("session.pkl"):
        try:
            with open("session.pkl", "rb") as f:
                session_data = pickle.load(f)
            brain_session.cookies.update(session_data["cookies"])
            brain_session.headers.update(session_data["headers"])
            print("Loaded stored session from disk.")
        except Exception as e:
            print(f"Failed to load session: {e}")

    time_to_live = ace.check_session_timeout(brain_session)

    if time_to_live >= duration:
        print(f"Session is valid. Expires in {time_to_live} seconds.")
        return brain_session

    print("Session expired or missing. Logging in...")
    brain_session = ace.start_session()

    with open("session.pkl", "wb") as f:
        pickle.dump(
            {"cookies": brain_session.cookies, "headers": brain_session.headers}, f
        )
    print("New session saved to disk.")
    return brain_session


def disable_progress_bar():
    class _DummyTqdm:
        def __init__(self, *args, **kwargs):
            self.total = kwargs.get("total", None)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def update(self, n=1):
            pass

        def set_description(self, *a, **kw):
            pass

        def close(self):
            pass

        def __iter__(self):
            return iter(())

        def __len__(self):
            return 0

    ace.tqdm.tqdm = _DummyTqdm


def get_power_pool_corr(s, alpha_id: str) -> pd.DataFrame:
    while True:
        result = s.get(
            ace.brain_api_url + "/alphas/" + alpha_id + "/correlations/power-pool"
        )
        if "retry-after" in result.headers:
            time.sleep(float(result.headers["Retry-After"]))
        else:
            break

    if result.json().get("records", 0) == 0:
        ace.logger.warning(
            f"Failed to get power pool correlation for alpha_id {alpha_id}. {result.json()}"
        )
        return pd.DataFrame()

    columns = [dct["name"] for dct in result.json()["schema"]["properties"]]
    power_pool_corr_df = pd.DataFrame(result.json()["records"], columns=columns).assign(
        alpha_id=alpha_id
    )
    power_pool_corr_df["alpha_max_power_pool_corr"] = result.json()["max"]
    power_pool_corr_df["alpha_min_power_pool_corr"] = result.json()["min"]
    return power_pool_corr_df


def create_tag_list(s, name: str, alpha_ids: list) -> dict:
    response = s.post(
        ace.brain_api_url + "/tags",
        json={"type": "LIST", "name": name, "alphas": alpha_ids},
    )
    if response.status_code not in (200, 201):
        ace.logger.warning(
            f"Failed to create tag list '{name}'. "
            f"Status code: {response.status_code}, Response: {response.text}"
        )
        return {}
    return response.json()


def get_datafield(s, datafield: str):
    resp = s.get(ace.brain_api_url + "/data-fields/" + datafield)
    return resp.json()


def simulate_single_alpha(brain_session, alpha: dict) -> dict:
    """Run one simulation with retry+backoff on WQ Brain 429 rate limits."""
    MAX_SIM_RETRIES = 5
    for attempt in range(1, MAX_SIM_RETRIES + 1):
        try:
            brain_session = ace.check_session_and_relogin(brain_session)
            simulation_response = ace.start_simulation(brain_session, alpha)
            simulation_result = ace.simulation_progress(brain_session, simulation_response)
            if not simulation_result["completed"]:
                return ""
            return simulation_result["result"]
        except Exception as e:
            err = str(e)
            is_429 = (
                "429" in err
                or "too many 429" in err.lower()
                or "Max retries exceeded" in err
                or "ResponseError" in err
            )
            if is_429 and attempt < MAX_SIM_RETRIES:
                wait = 30 * attempt  # 30s, 60s, 90s, 120s
                logging.warning(
                    f"[WQ Brain] 429 on /simulations — waiting {wait}s before retry {attempt}/{MAX_SIM_RETRIES}"
                )
                time.sleep(wait)
                continue
            logging.error(f"[WQ Brain] simulate_single_alpha failed (attempt {attempt}): {e}")
            return ""
    return ""


def simulate_alpha_list(
    brain_session,
    alpha_list: list,
    limit_of_concurrent_simulations: int = 5,
) -> list:
    if not (1 <= limit_of_concurrent_simulations <= 8):
        limit_of_concurrent_simulations = 5

    result_list = []
    with ThreadPool(limit_of_concurrent_simulations) as pool:
        with tqdm.tqdm(total=len(alpha_list)) as pbar:
            for result in pool.imap_unordered(
                partial(simulate_single_alpha, brain_session), alpha_list
            ):
                result_list.append(result)
                pbar.update()

    return result_list


def get_alpha_recordset(brain_session, alpha_id: str, recordset_type: str):
    while True:
        result = brain_session.get(
            ace.brain_api_url + "/alphas/" + alpha_id + f"/recordsets/{recordset_type}"
        )
        if "retry-after" in result.headers:
            time.sleep(float(result.headers["Retry-After"]))
        else:
            break

    recordset = result.json()
    return recordset["records"]
