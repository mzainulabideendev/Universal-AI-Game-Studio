"""Meshy AI integration using the documented public REST API.

Endpoints implemented (verified against https://docs.meshy.ai/en/api):
  GET  /openapi/v1/balance
  POST /openapi/v2/text-to-3d                  (preview / refine)
  GET  /openapi/v2/text-to-3d/{id}
  POST /openapi/v1/rigging
  GET  /openapi/v1/rigging/{id}
  GET  /openapi/v1/animations/library
  POST /openapi/v1/animations
  GET  /openapi/v1/animations/{id}

Generation costs credits, so every create call requires ``confirm=true``. The
API key is resolved from an explicit argument, the MESHY_API_KEY environment
variable, or a private local secret file; it is never echoed, audited or stored
in the studio config.
"""

from __future__ import annotations

import os
import time

from . import config, operations, secrets
from .util import (
    ToolError,
    expand,
    http_download,
    http_request,
    sha256_file,
)

API_ROOT = "https://api.meshy.ai/openapi"
API_HOSTS = ["api.meshy.ai"]
ASSET_HOSTS = ["assets.meshy.ai", "cdn.meshy.ai"]

TASK_ENDPOINTS = {
    "text-to-3d": f"{API_ROOT}/v2/text-to-3d",
    "rigging": f"{API_ROOT}/v1/rigging",
    "animation": f"{API_ROOT}/v1/animations",
}

TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELED"}


def api_key(explicit: str | None = None) -> str:
    key = secrets.resolve_meshy_key(explicit)
    if not key:
        raise ToolError(
            "MESHY_API_KEY is not configured. Call meshy_setup_guide for setup steps, "
            "then either set MESHY_API_KEY in the MCP server environment and reconnect, "
            "or call meshy_configure_api_key with confirm=true."
        )
    return key


def setup_guide() -> dict:
    """Return status and real setup/rotation steps without exposing the key."""
    source = secrets.meshy_key_source()
    return {
        "ok": True,
        "provider": "meshy",
        "configured": bool(source),
        "source": source,
        "env_var": secrets.MESHY_ENV,
        "local_key_file": secrets.meshy_key_file(),
        "credential_order": [
            "MESHY_API_KEY environment variable",
            "private local key file written by meshy_configure_api_key",
        ],
        "steps": [
            "Create or sign in to a Meshy account at https://www.meshy.ai/.",
            "Open the API Keys page: https://www.meshy.ai/developers/keys",
            "Click 'Create API Key', give it a name (for example 'game-studio'), and "
            "optionally set a monthly credit limit.",
            "Copy the key immediately. Meshy does not show it again after the dialog closes.",
            "Choose one storage method: (a) add MESHY_API_KEY to the MCP client's server "
            "environment and reconnect, or (b) give the key to this session and call "
            "meshy_configure_api_key with confirm=true to validate and save it locally.",
            "Call meshy_balance to confirm the key is accepted and see the credit balance.",
        ],
        "change_or_rotate": [
            "Create a new key on the same Meshy API Keys page.",
            "Call meshy_configure_api_key again with the new key and confirm=true; it "
            "replaces the local file atomically.",
            "If you use the environment variable instead, update it and restart/reconnect "
            "the MCP server. The environment variable overrides the local file.",
            "Revoke the old key on the Meshy API Keys page.",
            "Call meshy_clear_api_key to delete the local file when it is no longer needed.",
        ],
        "security": [
            "Never commit the key, paste it into a public issue, or include it in logs.",
            "The local file lives outside the repository under the studio config directory.",
            "Meshy keys can be given a monthly credit limit and an IP allowlist.",
            "If a key leaks, revoke it in the Meshy dashboard and create a replacement.",
        ],
        "tools": {
            "configure": "meshy_configure_api_key (validates against the balance endpoint, "
                         "then writes the private local file; requires confirm=true)",
            "clear": "meshy_clear_api_key (removes the local file; cannot remove an "
                     "environment variable)",
            "status": "meshy_setup_guide",
        },
        "next_action": (
            "Ask the user for their Meshy API key if they want local storage, then call "
            "meshy_configure_api_key. Do not ask them to post it publicly or commit it."
            if not source else
            "A key is configured. Do not reveal it; call meshy_balance to verify access."
        ),
        "docs": "https://docs.meshy.ai/en/api/authentication",
    }


def configure_api_key(value: str, *, confirm: bool = False) -> dict:
    """Validate a key against Meshy, then store it in the private local file."""
    if not confirm:
        raise ToolError("Saving an API key writes a local secret; pass confirm=true")
    cleaned = secrets.validate_api_key(value)
    check = balance(explicit_key=cleaned)
    if not check.get("ok"):
        return {
            "ok": False,
            "state": check.get("state") or "validation-failed",
            "error": check.get("error") or "Meshy rejected the API key",
            "remediation": check.get("remediation") or
                           "Check that the key is active and copied completely, then retry.",
            "saved": False,
            "status": check.get("status"),
        }
    saved = secrets.save_meshy_key(cleaned)
    payload = check.get("payload") if isinstance(check.get("payload"), dict) else {}
    config.audit("meshy.configure_api_key", tool="meshy_configure_api_key",
                 details={"source": "local-file", "validated": True})
    return {
        "ok": True,
        "state": "configured",
        "source": "local-file",
        "saved": True,
        "path": saved["path"],
        "validation": {"status": check.get("status"),
                       "credit_balance": payload.get("balance")},
        "note": "The key is stored outside the repository and is never returned by tools. "
                "The MESHY_API_KEY environment variable overrides it.",
    }


def clear_api_key() -> dict:
    removed = secrets.clear_local_meshy_key()
    source = secrets.meshy_key_source()
    return {
        "ok": True,
        "removed_local_file": removed,
        "configured": bool(source),
        "source": source,
        "note": ("The environment variable MESHY_API_KEY is still set and takes precedence; "
                 "remove it from the MCP client configuration and reconnect to disable Meshy."
                 if source == "environment" else
                 "No Meshy key remains configured." if not source else
                 "A local key is still configured."),
    }


def _headers(explicit_key: str | None = None) -> dict:
    return {"Authorization": f"Bearer {api_key(explicit_key)}"}


def _request(method: str, path: str, *, body: dict | None = None,
             api_key_override: str | None = None, timeout: int = 60) -> dict:
    url = path if path.startswith("https://") else f"{API_ROOT}{path}"
    try:
        headers = _headers(api_key_override)
    except ToolError as exc:
        return {"ok": False, "state": "not-configured", "error": str(exc),
                "remediation": "Set MESHY_API_KEY in the MCP server environment, then reconnect."}
    response = http_request(
        url, method=method, headers=headers, body=body,
        timeout=timeout, allowed_hosts=API_HOSTS,
    )
    if not response.get("ok"):
        payload = response.get("payload")
        message = response.get("error")
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error") or message
            error_type = payload.get("type") or payload.get("code")
            if error_type:
                message = f"{message} ({error_type})"
        response["error"] = message or f"HTTP {response.get('status')}"
        response["remediation"] = _remediation(response.get("status"))
    return response


def _remediation(status: int | None) -> str | None:
    return {
        400: "Check the request fields shown in the error message.",
        401: "MESHY_API_KEY is missing or invalid.",
        402: "The Meshy account has insufficient credits or is on a free plan.",
        403: "Content moderation blocked the prompt or image.",
        404: "The task ID does not exist or its files expired.",
        429: "Meshy rate limit reached; wait and retry.",
    }.get(status)


def balance(explicit_key: str | None = None) -> dict:
    if not (explicit_key or secrets.meshy_key_source()):
        return {"ok": False, "state": "not-configured",
                "error": "No Meshy API key is configured",
                "remediation": "Call meshy_setup_guide, then set MESHY_API_KEY in the "
                               "server environment or call meshy_configure_api_key with "
                               "confirm=true."}
    response = _request("GET", "/v1/balance", api_key_override=explicit_key, timeout=30)
    if response.get("ok"):
        response["state"] = "connected"
    return response


def create_text_to_3d(prompt: str, *, mode: str = "preview", preview_task_id: str | None = None,
                      ai_model: str | None = None, target_polycount: int | None = None,
                      should_remesh: bool | None = None, pose_mode: str | None = None,
                      target_formats: list[str] | None = None, enable_pbr: bool = True,
                      texture_resolution: str | None = None,
                      texture_prompt: str | None = None,
                      confirm: bool = False, explicit_key: str | None = None) -> dict:
    if not confirm:
        raise ToolError("Meshy generation consumes credits; pass confirm=true after approval")
    if mode not in ("preview", "refine"):
        raise ToolError("mode must be 'preview' or 'refine'")
    body: dict = {"mode": mode}
    if mode == "preview":
        prompt = (prompt or "").strip()
        if not prompt:
            raise ToolError("prompt is required for a preview task")
        if len(prompt) > 800:
            raise ToolError("prompt must be at most 800 characters")
        body["prompt"] = prompt
        for key, value in {
            "ai_model": ai_model, "target_polycount": target_polycount,
            "should_remesh": should_remesh, "pose_mode": pose_mode,
            "target_formats": target_formats,
        }.items():
            if value is not None:
                body[key] = value
    else:
        if not preview_task_id:
            raise ToolError("preview_task_id is required for a refine task")
        body["preview_task_id"] = preview_task_id
        body["enable_pbr"] = bool(enable_pbr)
        if target_formats:
            body["target_formats"] = target_formats
        if texture_resolution:
            if texture_resolution not in ("2k", "4k", "8k"):
                raise ToolError("texture_resolution must be 2k, 4k or 8k")
            body["texture_resolution"] = texture_resolution
        if texture_prompt:
            body["texture_prompt"] = texture_prompt[:800]
    response = _request("POST", "/v2/text-to-3d", body=body, api_key_override=explicit_key)
    if response.get("ok") and isinstance(response.get("payload"), dict):
        response["task_id"] = response["payload"].get("result")
        response["mode"] = mode
        response["request"] = {k: v for k, v in body.items() if k != "prompt"}
        response["prompt"] = body.get("prompt")
    return response


def create_rigging(*, input_task_id: str | None = None, model_url: str | None = None,
                   height_meters: float = 1.7, confirm: bool = False,
                   explicit_key: str | None = None) -> dict:
    if not confirm:
        raise ToolError("Rigging consumes credits; pass confirm=true after approval")
    if bool(input_task_id) == bool(model_url):
        raise ToolError("provide exactly one of input_task_id or model_url")
    body: dict = {"height_meters": height_meters}
    if input_task_id:
        body["input_task_id"] = input_task_id
    else:
        body["model_url"] = model_url
    response = _request("POST", "/v1/rigging", body=body, api_key_override=explicit_key)
    if response.get("ok") and isinstance(response.get("payload"), dict):
        response["task_id"] = response["payload"].get("result")
    return response


def animation_library(*, search: str | None = None, category: str | None = None,
                      action_ids: list[int] | None = None,
                      explicit_key: str | None = None) -> dict:
    params = []
    if search:
        params.append(f"search={_url_quote(search)}")
    if category:
        params.append(f"category={_url_quote(category)}")
    if action_ids:
        params.append("action_ids=" + ",".join(str(int(i)) for i in action_ids[:200]))
    path = "/v1/animations/library" + ("?" + "&".join(params) if params else "")
    return _request("GET", path, api_key_override=explicit_key, timeout=30)


def _url_quote(value: str) -> str:
    from urllib.parse import quote
    return quote(value, safe="")


def create_animation(*, rig_task_id: str, action_id: int | None = None,
                     action_ids: list[int] | None = None,
                     motion_task_id: str | None = None,
                     confirm: bool = False, explicit_key: str | None = None) -> dict:
    if not confirm:
        raise ToolError("Animation tasks consume credits; pass confirm=true after approval")
    provided = [x is not None for x in (action_id, action_ids, motion_task_id)]
    if sum(provided) != 1:
        raise ToolError("provide exactly one of action_id, action_ids or motion_task_id")
    body: dict = {"rig_task_id": rig_task_id}
    if action_id is not None:
        body["action_id"] = int(action_id)
    if action_ids is not None:
        if not (1 <= len(action_ids) <= 10):
            raise ToolError("action_ids must contain 1-10 entries")
        if len(set(action_ids)) != len(action_ids):
            raise ToolError("action_ids must not contain duplicates")
        body["action_ids"] = [int(i) for i in action_ids]
    if motion_task_id is not None:
        body["motion_task_id"] = motion_task_id
    response = _request("POST", "/v1/animations", body=body, api_key_override=explicit_key)
    if response.get("ok") and isinstance(response.get("payload"), dict):
        response["task_id"] = response["payload"].get("result")
    return response


def get_task(task_id: str, task_type: str, *, explicit_key: str | None = None) -> dict:
    if not task_id:
        raise ToolError("task_id is required")
    if task_type not in TASK_ENDPOINTS:
        raise ToolError(f"task_type must be one of {sorted(TASK_ENDPOINTS)}")
    response = _request("GET", f"{TASK_ENDPOINTS[task_type]}/{task_id}",
                        api_key_override=explicit_key, timeout=30)
    if response.get("ok") and isinstance(response.get("payload"), dict):
        payload = response["payload"]
        response["status"] = payload.get("status")
        response["progress"] = payload.get("progress")
        response["task_error"] = payload.get("task_error")
        response["output_urls"] = _output_urls(payload, task_type)
    return response


def _output_urls(payload: dict, task_type: str) -> dict:
    urls: dict = {}
    if task_type == "text-to-3d":
        for fmt, url in (payload.get("model_urls") or {}).items():
            urls[fmt] = url
        if payload.get("thumbnail_url"):
            urls["thumbnail"] = payload["thumbnail_url"]
        for index, texture in enumerate(payload.get("texture_urls") or []):
            for name, url in (texture or {}).items():
                urls[f"texture_{index}_{name}"] = url
    elif task_type == "rigging":
        result = payload.get("result") or {}
        for key in ("rigged_character_glb_url", "rigged_character_fbx_url"):
            if result.get(key):
                urls[key.replace("_url", "")] = result[key]
        for name, url in (result.get("basic_animations") or {}).items():
            if url:
                urls[name.replace("_url", "")] = url
    elif task_type == "animation":
        result = payload.get("result") or {}
        for key, url in result.items():
            if isinstance(url, str) and url:
                urls[key.replace("_url", "")] = url
    return urls


def wait_for_task(task_id: str, task_type: str, *, timeout_seconds: int = 120,
                  poll_seconds: float = 5.0, explicit_key: str | None = None,
                  operation_id: str | None = None) -> dict:
    if timeout_seconds < 0 or timeout_seconds > 1800:
        raise ToolError("timeout_seconds must be between 0 and 1800")
    deadline = time.time() + timeout_seconds
    attempts = 0
    last = None
    while True:
        attempts += 1
        if operation_id and operations.is_cancel_requested(operation_id):
            return {
                "ok": False,
                "status": "cancelled",
                "cancelled": True,
                "local_polling_stopped": True,
                "remote_cancel": {
                    "supported": False,
                    "confirmed": False,
                    "note": "Meshy does not expose a documented cancel endpoint in this "
                            "adapter, so stopping local polling is not a remote cancellation.",
                },
                "task_id": task_id,
                "polls": attempts,
            }
        last = get_task(task_id, task_type, explicit_key=explicit_key)
        if not last.get("ok"):
            return last
        status = last.get("status")
        if status in TERMINAL_STATUSES:
            last["waited_seconds"] = round(timeout_seconds - max(0, deadline - time.time()), 1)
            last["polls"] = attempts
            return last
        if time.time() >= deadline:
            last["ok"] = False
            last["state"] = "still-running"
            last["error"] = (f"task {task_id} is still {status} after {timeout_seconds}s; "
                             "poll again with meshy_task_status")
            last["polls"] = attempts
            return last
        time.sleep(min(poll_seconds, max(0.0, deadline - time.time())))


def cancel_task(task_id: str, task_type: str, *, confirm: bool = False,
                explicit_key: str | None = None) -> dict:
    """Honest cancellation capability report.

    The documented Meshy API used here has no cancellation endpoint. This
    function never fabricates a remote cancellation. It returns ``ok: false``
    with the required next steps.
    """
    if not confirm:
        raise ToolError("cancelling a Meshy task requires explicit confirm=true")
    return {
        "ok": False,
        "status": "unsupported",
        "task_id": task_id,
        "task_type": task_type,
        "remote_cancel": False,
        "error": "no documented Meshy cancellation endpoint is implemented, so a remote "
                 "Meshy task was NOT cancelled",
        "supported_alternative": [
            "stop local polling with cancel_operation on the waiting operation",
            "delete unused generated outputs after the task finishes",
            "cancel through the Meshy web dashboard if the provider offers it",
        ],
        "note": "Credits already spent by a running task are not refunded by this server.",
    }


def download_output(task_id: str, task_type: str, output_key: str, destination: str,
                    *, explicit_key: str | None = None) -> dict:
    task = get_task(task_id, task_type, explicit_key=explicit_key)
    if not task.get("ok"):
        return task
    if task.get("status") != "SUCCEEDED":
        return {"ok": False, "error": f"task is {task.get('status')}, not SUCCEEDED",
                "status": task.get("status"), "progress": task.get("progress")}
    urls = task.get("output_urls") or {}
    if output_key not in urls:
        return {"ok": False, "error": f"output {output_key!r} not available",
                "available": sorted(urls)}
    target = os.path.abspath(expand(destination))
    result = http_download(urls[output_key], target, allowed_hosts=ASSET_HOSTS,
                           timeout=300, max_bytes=1024 * 1024 * 1024)
    if result.get("ok"):
        result["task_id"] = task_id
        result["task_type"] = task_type
        result["output_key"] = output_key
        result["sha256"] = sha256_file(target)
    return result


def generate_asset(prompt: str, *, refine: bool = False, wait: bool = True,
                   timeout_seconds: int = 180, ai_model: str | None = None,
                   target_polycount: int | None = None, pose_mode: str | None = None,
                   enable_pbr: bool = True, texture_resolution: str | None = None,
                   confirm: bool = False, explicit_key: str | None = None) -> dict:
    """Preview (and optionally refine) a text prompt. Returns real task status."""
    preview = create_text_to_3d(
        prompt, mode="preview", ai_model=ai_model, target_polycount=target_polycount,
        pose_mode=pose_mode, target_formats=["glb", "fbx"],
        confirm=confirm, explicit_key=explicit_key,
    )
    if not preview.get("ok"):
        return preview
    result = {"ok": True, "preview": preview, "refine": None,
              "next_step": "Call meshy_task_status with task_type=text-to-3d, then "
                           "meshy_download_output with the task's GLB/FBX URL."}
    if wait:
        waited = wait_for_task(preview["task_id"], "text-to-3d",
                               timeout_seconds=timeout_seconds, explicit_key=explicit_key)
        result["preview"] = waited
        if not waited.get("ok") or waited.get("status") != "SUCCEEDED":
            result["ok"] = bool(waited.get("ok"))
            return result
    if refine:
        refine_response = create_text_to_3d(
            prompt, mode="refine", preview_task_id=preview["task_id"],
            enable_pbr=enable_pbr, texture_resolution=texture_resolution,
            target_formats=["glb", "fbx"], confirm=True, explicit_key=explicit_key,
        )
        result["refine"] = refine_response
        if refine_response.get("ok") and wait:
            result["refine"] = wait_for_task(
                refine_response["task_id"], "text-to-3d",
                timeout_seconds=timeout_seconds, explicit_key=explicit_key,
            )
        if not refine_response.get("ok"):
            result["ok"] = False
    return result
