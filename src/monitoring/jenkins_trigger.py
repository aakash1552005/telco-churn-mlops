"""Jenkins Retraining Pipeline Trigger Module.

Provides authenticated triggering of Jenkins CI/CD
retraining pipeline via remote REST API.
Handles CSRF crumb issuance, HTTP basic authentication
via environment/secrets, and structured logging.
"""

import base64
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def get_jenkins_auth() -> Optional[str]:
    """Retrieve Jenkins authentication string (user:token) from environment or file.

    Priority:
        1. JENKINS_AUTH environment variable (format: 'admin:token')
        2. Settings.JENKINS_AUTH
        3. JENKINS_USER and JENKINS_API_TOKEN environment variables
        4. /var/jenkins_home/cli_token.txt if running
           inside/adjacent to Jenkins container
    """
    if "JENKINS_AUTH" in os.environ and os.environ["JENKINS_AUTH"]:
        return os.environ["JENKINS_AUTH"]

    cfg_auth = get_settings().JENKINS_AUTH
    if cfg_auth and cfg_auth.strip():
        return cfg_auth

    user = os.getenv("JENKINS_USER")
    token = os.getenv("JENKINS_API_TOKEN")
    if user and token:
        return f"{user}:{token}"

    token_file = Path("/var/jenkins_home/cli_token.txt")
    if token_file.exists():
        try:
            return token_file.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning(f"Failed to read token from '{token_file}': {e}")

    # Fallback to dev default if running in local testing environment
    return os.getenv("DEFAULT_JENKINS_AUTH", "admin:admin")


def get_jenkins_base_url() -> str:
    """Retrieve Jenkins Base URL from settings or environment."""
    return (
        os.getenv("JENKINS_URL")
        or get_settings().JENKINS_URL
        or "http://localhost:8081"
    ).rstrip("/")


def trigger_jenkins_retraining(
    job_name: Optional[str] = None,
    reason: Optional[List[str]] = None,
    jenkins_url: Optional[str] = None,
    auth_credentials: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Dispatch an authenticated HTTP POST to Jenkins.

    Triggers pipeline execution.

    Args:
        job_name: Target Jenkins job identifier.
        reason: List of triggered drift criteria that provoked the build.
        jenkins_url: Optional override for Jenkins base URL.
        auth_credentials: Optional override for 'username:token' auth string.
        parameters: Optional dict of job parameters for parameterized builds.

    Returns:
        Dictionary containing trigger status, response code, and headers.

    Raises:
        RuntimeError: If authentication is missing or Jenkins API call fails.
    """
    target_job = job_name or get_settings().JENKINS_JOB_NAME
    base_url = jenkins_url or get_jenkins_base_url()
    auth = auth_credentials if auth_credentials is not None else get_jenkins_auth()

    if not auth or not auth.strip():
        raise RuntimeError(
            "Cannot trigger Jenkins retraining: "
            "No authentication credentials found in "
            "JENKINS_AUTH, JENKINS_USER/JENKINS_API_TOKEN,"
            " or /var/jenkins_home/cli_token.txt."
        )

    logger.info(
        f"Initiating Jenkins retraining trigger for job '{target_job}' at '{base_url}'"
    )

    # Encode HTTP Basic Auth
    b64_auth = base64.b64encode(auth.encode("utf-8")).decode("utf-8")
    headers: Dict[str, str] = {
        "Authorization": f"Basic {b64_auth}",
    }

    # 1. Fetch CSRF Crumb
    crumb_url = (
        f'{base_url}/crumbIssuer/api/xml?xpath=concat(//crumbRequestField,":",//crumb)'
    )

    try:
        crumb_req = urllib.request.Request(crumb_url, headers=headers)
        with urllib.request.urlopen(crumb_req, timeout=10) as resp:
            crumb_text = resp.read().decode("utf-8").strip()
            if ":" in crumb_text:
                parts = crumb_text.split(":", 1)
                hdr_name: str = parts[0]
                hdr_val: str = parts[1]
                headers[hdr_name] = hdr_val
                logger.debug(f"Acquired Jenkins CSRF crumb: '{hdr_name}'")
    except Exception as e:
        logger.warning(
            f"CSRF crumb acquisition failed ({e}). Proceeding without crumb header."
        )

    # 2. Trigger Build
    if parameters:
        query = urllib.parse.urlencode(parameters)
        build_url = f"{base_url}/job/{target_job}/buildWithParameters?{query}"
    else:
        build_url = f"{base_url}/job/{target_job}/build"

    try:
        build_req = urllib.request.Request(
            build_url,
            data=b"",
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(build_req, timeout=15) as resp:
            status_code = resp.status
            queue_location = resp.headers.get("Location", "")
            logger.info(
                f"Successfully triggered Jenkins build "
                f"for '{target_job}'. HTTP status: {status_code}",
                extra={
                    "job_name": target_job,
                    "status_code": status_code,
                    "queue_location": queue_location,
                },
            )
            return {
                "status": "success",
                "status_code": status_code,
                "job_name": target_job,
                "queue_location": queue_location,
                "reason": reason or [],
            }
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            pass
        err_msg = (
            f"Jenkins API trigger failed with HTTP {e.code} "
            f"({e.reason}) at '{build_url}'. "
            f"Response body: {err_body}"
        )
        logger.error(err_msg)
        raise RuntimeError(err_msg) from e
    except Exception as e:
        err_msg = f"Unexpected error connecting to Jenkins at '{build_url}': {e}"
        logger.error(err_msg)
        raise RuntimeError(err_msg) from e
