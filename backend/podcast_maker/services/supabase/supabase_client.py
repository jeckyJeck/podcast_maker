import os
import httpx
from httpx import Timeout

from dotenv import load_dotenv
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from podcast_maker.core.paths import BACKEND_ROOT
from podcast_maker.core.logging_config import get_logger


load_dotenv(dotenv_path=BACKEND_ROOT / ".env")

_supabase_client: Client | None = None
logger = get_logger()


def get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    anon_key = os.getenv("SUPABASE_ANON_KEY")

    key = service_role_key

    if not url or not key:
        raise RuntimeError("Supabase configuration missing. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")

    if service_role_key:
        logger.info("supabase_client_initialized auth_mode=service_role")
    else:
        logger.warning("supabase_client_initialized auth_mode=anon_key writes_may_fail_due_to_rls=true")

    # Supabase calls include status polling, progress writes, and file uploads.
    timeout = Timeout(180.0, connect=20.0, read=180.0, write=180.0, pool=20.0)
    http_client = httpx.Client(timeout=timeout)

    options = SyncClientOptions(httpx_client=http_client)
    _supabase_client = create_client(url, key, options)
    return _supabase_client
