"""Run on the user's PC and execute only jobs leased to its paired CLI device."""
import argparse
import base64
import os
import time
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException


def api_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    local_http = parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if (parsed.scheme != "https" and not local_http) or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("API origin must be an HTTPS origin")
    return value.rstrip("/")


def message(response: httpx.Response) -> str:
    if response.status_code == 401:
        return "PC 연결이 만료됐거나 해제됐습니다. 웹의 AI 연결 설정에서 새 연결 코드를 만든 뒤 다시 실행해 주세요."
    if response.status_code == 409:
        return "웹의 PC CLI 설정 또는 연결 상태가 바뀌었습니다. 설정을 다시 저장해 주세요."
    return "서버와 PC 커넥터를 연결하지 못했습니다. 네트워크와 API 주소를 확인해 주세요."


def request(client: httpx.Client, method: str, origin: str, path: str, *, token: str | None = None, pairing: str | None = None, body=None):
    headers = {}
    if token:
        headers["X-Dudri-Connector"] = token
    if pairing:
        headers["X-Dudri-Pairing-Code"] = pairing
    response = client.request(method, origin + path, headers=headers, json=body)
    if not response.is_success:
        raise RuntimeError(message(response))
    return response.json() if response.status_code != 204 else None


def failure_reason(error: Exception) -> str:
    if isinstance(error, HTTPException):
        if error.status_code == 504:
            return "timeout"
        if error.status_code == 409:
            return "connection_changed"
        if error.status_code == 503:
            return "cli_unavailable"
    return "generation_failed"


def execute_job(client, origin, token, job):
    # Import after local-only environment variables are set in main().
    from .ai import AIProvider
    from .site_prompts import site_prompt
    from .sites import Generated

    images = []
    try:
        for item in job["reference_images"]:
            images.append({"name": item["name"], "content_type": item["content_type"],
                           "content": base64.b64decode(item["content"], validate=True)})
        cli = job["cli"]
        provider = AIProvider("cli", cli_provider=cli["provider"], cli_model=cli["model"],
                              cli_connection=cli["connection"])
        inputs = {**job["snapshot"], "kind": job["site_kind"], "request": job["instruction"],
                  "previous_code": job["previous_code"], "reference_materials": job["reference_materials"],
                  "reference_images": [{"name": image["name"], "content_type": image["content_type"]} for image in images]}
        result = provider.generate(site_prompt(job["site_kind"]), inputs, Generated, complexity="hard", image_attachments=images)
        request(client, "POST", origin, f'/api/v1/ai-cli-connectors/jobs/{job["job_id"]}/complete', token=token,
                body={"lease_token": job["lease_token"], "document": result.document.model_dump(),
                      "code": result.code.model_dump(), "model": provider.last_model})
        print("[connector] A PC CLI document job was saved.", flush=True)
    except (HTTPException, KeyError, TypeError, ValueError, UnicodeError, RuntimeError) as error:
        try:
            request(client, "POST", origin, f'/api/v1/ai-cli-connectors/jobs/{job["job_id"]}/fail', token=token,
                    body={"lease_token": job["lease_token"], "reason": failure_reason(error)})
        except RuntimeError:
            pass
        print("[connector] The CLI job could not finish. Check the AI connection settings and try again.", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Dudri local CLI connector")
    parser.add_argument("--connector", required=True, metavar="PAIRING_CODE", help="one-time code shown in AI connection settings")
    parser.add_argument("--api-origin", required=True)
    args = parser.parse_args()
    try:
        origin = api_origin(args.api_origin)
    except ValueError:
        print("[connector] Use the HTTPS API address shown in the AI connection settings.", flush=True)
        return 2

    # A connector never loads production service credentials or starts an API.
    # These values make the official CLI adapter available on this PC only.
    os.environ["DUDRI_ENVIRONMENT"] = "development"
    os.environ["DUDRI_APP_ORIGIN"] = "http://localhost:3000"
    os.environ["DUDRI_SITE_ORIGIN"] = "http://127.0.0.1:8001"
    from .cli_metadata import probe_cli

    try:
        connections = [probe_cli(family) for family in ("codex", "claude")]
        device_id = connections[0]["device_id"]
        device_name = connections[0]["device_name"]
        with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
            activation = request(client, "POST", origin, "/api/v1/ai-cli-connectors/activate", pairing=args.connector,
                                 body={"device_id": device_id, "device_name": device_name, "connections": connections})
            token = activation["connector_token"]
            print("[connector] Connected. Keep this window open while using PC CLI generation.", flush=True)
            while True:
                claimed = request(client, "POST", origin, "/api/v1/ai-cli-connectors/jobs/claim", token=token)
                if claimed.get("job"):
                    execute_job(client, origin, token, claimed["job"])
                else:
                    time.sleep(2)
    except KeyboardInterrupt:
        print("\n[connector] Stopped. No CLI credentials were stored by Dudri.", flush=True)
        return 0
    except RuntimeError as error:
        print(f"[connector] {error}", flush=True)
        return 1
    except (OSError, httpx.HTTPError, KeyError, TypeError, ValueError):
        print("[connector] Could not start. Check the official CLI login and network, then create a new connection code.", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
