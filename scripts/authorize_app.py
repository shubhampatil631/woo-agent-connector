"""WooCommerce App-Authorization flow helper.

Runs a local callback server to complete the WooCommerce OAuth-style app authorization flow,
capturing generated read-only credentials and persisting them to .env.
"""

import logging
import os
from urllib.parse import urlencode

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("wc-auth-helper")

app = FastAPI(title="WooCommerce App Authorize Callback")

STORE_URL = os.getenv("WOO_BASE_URL", os.getenv("WOO_STORE_URL", "http://localhost:8080")).rstrip("/")
LOCAL_PORT = 8000
CALLBACK_URL = f"http://localhost:{LOCAL_PORT}/callback"
RETURN_URL = f"http://localhost:{LOCAL_PORT}/success"


class CallbackPayload(BaseModel):
    key_id: int | None = None
    user_id: int | None = None
    consumer_key: str
    consumer_secret: str
    key_permissions: str = "read"


received_credentials: dict[str, str] = {}
server_instance: uvicorn.Server | None = None


def save_credentials_to_env(key: str, secret: str, permissions: str) -> None:
    env_file = ".env"
    existing_lines = []
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            existing_lines = f.readlines()

    keys_to_update = {
        "WOO_BASE_URL": STORE_URL,
        "WOO_CONSUMER_KEY": key,
        "WOO_CONSUMER_SECRET": secret,
        "WOO_AUTH_TYPE": "api_key",
    }

    new_lines = []
    found_keys = set()
    for line in existing_lines:
        line_clean = line.strip()
        if "=" in line_clean and not line_clean.startswith("#"):
            k = line_clean.split("=", 1)[0].strip()
            if k in keys_to_update:
                new_lines.append(f"{k}={keys_to_update[k]}\n")
                found_keys.add(k)
                continue
        new_lines.append(line)

    for k, v in keys_to_update.items():
        if k not in found_keys:
            new_lines.append(f"{k}={v}\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    logger.info("Saved credentials to %s (permissions: %s)", env_file, permissions)


@app.post("/callback")
async def handle_callback(request: Request):
    """Callback endpoint invoked by WooCommerce to deliver generated keys."""
    data = await request.json()
    logger.info("Received WooCommerce authorization callback payload.")

    consumer_key = data.get("consumer_key", "")
    consumer_secret = data.get("consumer_secret", "")
    permissions = data.get("key_permissions", "read")

    if not consumer_key or not consumer_secret:
        return JSONResponse(status_code=400, content={"error": "Missing key or secret"})

    received_credentials["consumer_key"] = consumer_key
    received_credentials["consumer_secret"] = consumer_secret
    received_credentials["permissions"] = permissions

    save_credentials_to_env(consumer_key, consumer_secret, permissions)

    return JSONResponse(status_code=200, content={"status": "success", "permissions": permissions})


@app.get("/success")
async def handle_success():
    """Return landing page displayed after WooCommerce user approves the app."""
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html>
        <head><title>Authorization Successful</title></head>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h2>WooCommerce App Authorized Successfully</h2>
            <p>Read-only credentials were saved to your local <code>.env</code> file.</p>
            <p>You can close this tab and return to your terminal.</p>
        </body>
        </html>
        """
    )


def build_authorize_url() -> str:
    params = {
        "app_name": "Agent Studio Connector",
        "scope": "read",
        "user_id": "1",
        "return_url": RETURN_URL,
        "callback_url": CALLBACK_URL,
    }
    return f"{STORE_URL}/wc-auth/v1/authorize?{urlencode(params)}"


def main():
    auth_url = build_authorize_url()
    print("===================================================================")
    print("  WooCommerce App Authorization Flow Helper                        ")
    print("===================================================================")
    print(f"1. Ensure your WooCommerce store is running at: {STORE_URL}")
    print("2. Open the following URL in your browser to authorize:")
    print(f"\n   {auth_url}\n")
    print(f"3. Waiting for WooCommerce callback on port {LOCAL_PORT}...")
    print("===================================================================")

    config = uvicorn.Config(app=app, host="0.0.0.0", port=LOCAL_PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
