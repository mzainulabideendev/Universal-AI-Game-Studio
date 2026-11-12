"""Asset discovery, licensing, download and file validation.

Only providers with a real public API are searched. Providers whose terms or
APIs make automated search impossible (Mixamo, Kenney, OpenGameArt, Unity Asset
Store, Fab) are reported as ``manual-only`` instead of being simulated.

Poly Haven assets are documented as CC0. Sketchfab results carry the license
reported by its API; when that field is absent the asset is marked unknown and
must not be shipped without manual review.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import urllib.parse

from . import secrets
from .util import (
    ToolError,
    expand,
    http_download,
    http_request,
    now_iso,
    read_json,
    safe_join,
    sha256_file,
    write_json,
)

POLYHAVEN_HOSTS = ["api.polyhaven.com", "dl.polyhaven.org", "cdn.polyhaven.com"]
SKETCHFAB_HOSTS = ["api.sketchfab.com", "media.sketchfab.com"]
POLYHAVEN_API = "https://api.polyhaven.com"
POLYHAVEN_LICENSE = {
    "id": "CC0-1.0",
    "name": "Creative Commons Zero 1.0 Universal",
    "url": "https://creativecommons.org/publicdomain/zero/1.0/",
    "source": "https://polyhaven.com/license",
    "commercial_use": True,
    "attribution_required": False,
    "redistribution": "allowed",
}
SKETCHFAB_UNKNOWN_LICENSE = {
    "id": "unknown",
    "name": "Not reported by the API response",
    "commercial_use": None,
    "attribution_required": None,
    "redistribution": None,
    "source": "https://sketchfab.com/licenses",
}

PROVIDERS = [
    {
        "id": "polyhaven", "name": "Poly Haven", "kinds": ["model", "texture", "hdri"],
        "api": "https://api.polyhaven.com", "automated_search": True,
        "automated_download": True, "license": "CC0-1.0",
        "auth": "none", "state": "available",
    },
    {
        "id": "sketchfab", "name": "Sketchfab", "kinds": ["model", "character", "environment", "animation"],
        "api": "https://api.sketchfab.com/v3", "automated_search": True,
        "automated_download": False, "license": "per-asset", "auth": "SKETCHFAB_TOKEN (optional for public search)",
        "state": "configured" if os.environ.get("SKETCHFAB_TOKEN") else "search-may-work-publicly",
    },
    {
        "id": "meshy", "name": "Meshy AI", "kinds": ["model", "character", "texture", "rig", "animation"],
        "api": "https://api.meshy.ai/openapi", "automated_search": False,
        "automated_download": True, "license": "Meshy terms of service",
        "auth": "MESHY_API_KEY",
        "state": "configured" if secrets.meshy_key_source() else "not-configured",
    },
    {
        "id": "mixamo", "name": "Mixamo", "kinds": ["character", "animation"],
        "automated_search": False, "automated_download": False,
        "license": "Adobe terms", "auth": "Adobe account (no public API)",
        "state": "manual-only",
        "reason": "Mixamo has no documented public search/download API. Use the website with an authorized account and record the license.",
    },
    {
        "id": "kenney", "name": "Kenney", "kinds": ["model", "2d", "audio", "ui"],
        "automated_search": False, "automated_download": False,
        "license": "per-pack (usually CC0)", "auth": "none (website)",
        "state": "manual-only",
        "reason": "No documented catalogue API. Download from kenney.nl and record each pack's license.",
    },
    {
        "id": "opengameart", "name": "OpenGameArt", "kinds": ["model", "2d", "audio"],
        "automated_search": False, "automated_download": False,
        "license": "per-asset", "auth": "none (website)",
        "state": "manual-only",
        "reason": "No documented JSON API and scraping is not assumed permitted. Review each asset page manually.",
    },
    {
        "id": "unity_asset_store", "name": "Unity Asset Store", "kinds": ["model", "2d", "audio", "ui", "tool"],
        "automated_search": False, "automated_download": False,
        "license": "Unity Asset Store EULA", "auth": "Unity account",
        "state": "manual-only",
        "reason": "Purchases and downloads require an authorized Unity account; automated purchase is intentionally unsupported.",
    },
    {
        "id": "fab", "name": "Fab", "kinds": ["model", "2d", "audio", "tool"],
        "automated_search": False, "automated_download": False,
        "license": "Fab EULA / per-asset", "auth": "Epic account",
        "state": "manual-only",
        "reason": "No public download API; purchases require explicit user approval.",
    },
]


PROVIDER_SITES = {
    "polyhaven": "https://polyhaven.com",
    "sketchfab": "https://sketchfab.com",
    "meshy": "https://www.meshy.ai",
    "mixamo": "https://www.mixamo.com",
    "kenney": "https://kenney.nl",
    "opengameart": "https://opengameart.org",
    "unity_asset_store": "https://assetstore.unity.com",
    "fab": "https://www.fab.com",
}


def providers() -> dict:
    items = []
    for provider in PROVIDERS:
        record = dict(provider)
        if record["id"] == "meshy":
            record["state"] = ("configured" if secrets.meshy_key_source()
                               else "not-configured")
            record["setup_tool"] = "meshy_setup_guide"
        elif record["id"] == "sketchfab":
            record["state"] = ("configured" if os.environ.get("SKETCHFAB_TOKEN")
                               else "search-may-work-publicly")
        items.append(record)
    return {
        "ok": True,
        "providers": items,
        "note": "Only providers with automated_search=true can be searched by this tool. "
                "manual-only providers must be handled by the user in a browser with the "
                "provider's own account and terms.",
    }


# --------------------------------------------------------------------------
# Poly Haven
# --------------------------------------------------------------------------
def _polyhaven_assets(asset_type: str) -> dict:
    if asset_type not in ("models", "textures", "hdris"):
        raise ToolError("asset_type must be models, textures or hdris")
    response = http_request(f"{POLYHAVEN_API}/assets?t={asset_type}", timeout=45,
                            allowed_hosts=POLYHAVEN_HOSTS)
    if not response.get("ok"):
        raise ToolError(f"Poly Haven API failed: {response.get('error') or response.get('status')}")
    payload = response.get("payload")
    if not isinstance(payload, dict):
        raise ToolError("Poly Haven returned an unexpected payload")
    return payload


def search_polyhaven(query: str = "", *, asset_type: str = "models", limit: int = 20,
                     min_polycount: int | None = None, max_polycount: int | None = None) -> dict:
    if limit < 1 or limit > 60:
        raise ToolError("limit must be between 1 and 60")
    assets = _polyhaven_assets(asset_type)
    words = [w for w in (query or "").lower().split() if w]
    results = []
    for asset_id, asset in assets.items():
        if not isinstance(asset, dict):
            continue
        polycount = asset.get("polycount")
        if min_polycount is not None and (polycount is None or polycount < min_polycount):
            continue
        if max_polycount is not None and polycount is not None and polycount > max_polycount:
            continue
        haystack = " ".join([
            asset_id, str(asset.get("name", "")), str(asset.get("description", "")),
            " ".join(asset.get("tags", []) or []), " ".join(asset.get("categories", []) or []),
            str(asset.get("category", "")),
        ]).lower()
        score = sum(3 if word in str(asset.get("name", "")).lower() else 1
                    for word in words if word in haystack)
        if words and score == 0:
            continue
        results.append({
            "provider": "polyhaven",
            "asset_id": asset_id,
            "name": asset.get("name") or asset_id,
            "kind": asset_type[:-1],
            "categories": asset.get("categories") or [],
            "category": asset.get("category"),
            "tags": (asset.get("tags") or [])[:20],
            "authors": asset.get("authors") or {},
            "polycount": polycount,
            "dimensions_mm": asset.get("dimensions"),
            "max_resolution": asset.get("max_resolution"),
            "thumbnail_url": asset.get("thumbnail_url"),
            "source_url": f"https://polyhaven.com/a/{asset_id}",
            "license": POLYHAVEN_LICENSE,
            "download_count": asset.get("download_count"),
            "score": score,
        })
    results.sort(key=lambda r: (-r["score"], -(r.get("download_count") or 0)))
    return {
        "ok": True,
        "provider": "polyhaven",
        "query": query,
        "asset_type": asset_type,
        "total_matches": len(results),
        "returned": min(limit, len(results)),
        "results": results[:limit],
        "license_note": "Poly Haven publishes its library as CC0. Verify the asset page before shipping.",
    }


def sketchfab_search(query: str, *, limit: int = 20, downloadable: bool = True,
                     animated: bool | None = None) -> dict:
    if limit < 1 or limit > 24:
        raise ToolError("Sketchfab limit must be between 1 and 24 per page")
    params = {"type": "models", "q": query, "count": min(limit, 24)}
    if downloadable:
        params["downloadable"] = "true"
    if animated is not None:
        params["animated"] = "true" if animated else "false"
    url = "https://api.sketchfab.com/v3/search?" + urllib.parse.urlencode(params)
    headers = {}
    token = os.environ.get("SKETCHFAB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Token {token}"
    response = http_request(url, headers=headers, timeout=45, allowed_hosts=SKETCHFAB_HOSTS)
    if not response.get("ok"):
        if response.get("status") in (401, 403):
            return {"ok": False, "state": "not-configured",
                    "error": "Sketchfab requires a token for this request",
                    "remediation": "Set SKETCHFAB_TOKEN in the MCP server environment."}
        return {"ok": False, "state": "error", "error": response.get("error") or response.get("status")}
    payload = response.get("payload") or {}
    results = []
    for item in (payload.get("results") or [])[:limit]:
        license_info = item.get("license") or {}
        if license_info:
            license_record = {
                "id": license_info.get("uid") or license_info.get("slug") or "unknown",
                "name": license_info.get("label") or license_info.get("name"),
                "url": license_info.get("url"),
                "commercial_use": None,
                "attribution_required": None,
                "redistribution": None,
                "source": "Sketchfab API license field; read the linked terms",
            }
        else:
            license_record = dict(SKETCHFAB_UNKNOWN_LICENSE)
        results.append({
            "provider": "sketchfab",
            "asset_id": item.get("uid"),
            "name": item.get("name"),
            "kind": "model",
            "author": (item.get("user") or {}).get("displayName"),
            "source_url": item.get("viewerUrl") or item.get("uri"),
            "thumbnail_url": ((item.get("thumbnails") or {}).get("images") or [{}])[0].get("url"),
            "face_count": item.get("faceCount"),
            "vertex_count": item.get("vertexCount"),
            "is_downloadable": item.get("isDownloadable"),
            "animation_count": item.get("animationCount"),
            "license": license_record,
            "license_warning": None if license_info else
                "Sketchfab did not report a license; treat as unknown and do not ship.",
        })
    return {"ok": True, "provider": "sketchfab", "query": query,
            "total_matches": (payload.get("totalCount") or len(results)),
            "results": results,
            "download_note": "Sketchfab downloads require an authenticated account and the "
                             "asset's download permission. This tool does not bypass that."}


def search_assets(query: str, *, kind: str = "model", provider: str = "auto",
                  limit: int = 20, max_polycount: int | None = None) -> dict:
    kind = (kind or "model").lower()
    provider = (provider or "auto").lower()
    sections = {}
    if provider in ("auto", "polyhaven"):
        if kind in ("model", "texture", "hdri"):
            asset_type = {"model": "models", "texture": "textures", "hdri": "hdris"}[kind]
            try:
                sections["polyhaven"] = search_polyhaven(
                    query, asset_type=asset_type, limit=limit, max_polycount=max_polycount)
            except ToolError as exc:
                sections["polyhaven"] = {"ok": False, "error": str(exc)}
        else:
            sections["polyhaven"] = {"ok": False,
                                     "error": f"Poly Haven does not provide {kind}"}
    if provider in ("auto", "sketchfab") and kind in ("model", "character", "environment", "animation"):
        sections["sketchfab"] = sketchfab_search(query, limit=min(limit, 24))
    if provider not in ("auto", "polyhaven", "sketchfab"):
        known = {p["id"] for p in PROVIDERS}
        if provider not in known:
            raise ToolError(f"unknown provider: {provider}")
        info = next(p for p in PROVIDERS if p["id"] == provider)
        sections[provider] = {
            "ok": False, "state": info["state"], "manual_only": True,
            "reason": info.get("reason") or "This provider has no automated search API.",
            "source_url": PROVIDER_SITES.get(provider, "https://example.invalid"),
        }
    return {
        "ok": True,
        "query": query,
        "kind": kind,
        "providers": sections,
        "searched_at": now_iso(),
        "warning": "Search results are candidates, not approval. Check the exact license and "
                   "technical fit before use.",
    }


# --------------------------------------------------------------------------
# downloads
# --------------------------------------------------------------------------
_ASSET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _safe_asset_id(asset_id: str) -> str:
    """Validate a provider asset id before it becomes a local directory name."""
    value = str(asset_id or "")
    if not _ASSET_ID.fullmatch(value) or value in (".", ".."):
        raise ToolError(f"invalid asset_id: {asset_id!r}")
    return value


def _safe_include_target(target_dir: str, relative: str) -> str:
    """Resolve a provider-supplied include path under the asset directory."""
    rel_clean = str(relative or "").replace("\\", "/").lstrip("/")
    if not rel_clean or ".." in rel_clean.split("/"):
        raise ToolError(f"provider included an unsafe relative path: {relative}")
    return safe_join(target_dir, rel_clean)


def _pick_polyhaven_file(files: dict, fmt: str, resolution: str) -> dict | None:
    fmt = fmt.lower()
    if fmt == "glb":
        # Poly Haven often exposes glTF + bin; a true .glb is preferred when present.
        candidates = [("glb", files.get("glb")), ("gltf", files.get("gltf"))]
    else:
        candidates = [(fmt, files.get(fmt))]
    for name, tree in candidates:
        if not tree:
            continue
        resolutions = tree if isinstance(tree, dict) else {}
        if resolution in resolutions:
            inner = resolutions[resolution]
        else:
            # pick the closest available resolution at or below the request
            order = ["1k", "2k", "4k", "8k"]
            available = [r for r in order if r in resolutions]
            if not available:
                continue
            inner = resolutions[available[-1]]
        for key, value in inner.items():
            if isinstance(value, dict) and value.get("url"):
                return {"format": name, "resolution": resolution,
                        "url": value["url"], "size": value.get("size"),
                        "md5": value.get("md5"),
                        "include": value.get("include") or {}}
    return None


def download_polyhaven(asset_id: str, *, fmt: str = "glb", resolution: str = "2k",
                       destination_dir: str | None = None,
                       confirm: bool = False, max_bytes: int = 512 * 1024 * 1024) -> dict:
    if not confirm:
        raise ToolError("Downloading assets writes files; pass confirm=true after approval")
    asset_id = _safe_asset_id(asset_id)
    response = http_request(f"{POLYHAVEN_API}/files/{urllib.parse.quote(asset_id)}",
                            timeout=45, allowed_hosts=POLYHAVEN_HOSTS)
    if not response.get("ok") or not isinstance(response.get("payload"), dict):
        return {"ok": False, "error": response.get("error") or "could not read Poly Haven files"}
    selected = _pick_polyhaven_file(response["payload"], fmt, resolution)
    if not selected:
        return {"ok": False, "error": f"no {fmt} file at {resolution} for {asset_id}",
                "available_formats": sorted(response["payload"].keys())}
    from .config import load_config
    root = os.path.abspath(expand(destination_dir or os.path.join(load_config()["download_root"], "polyhaven")))
    target_dir = safe_join(root, asset_id)
    relative = os.path.basename(urllib.parse.urlparse(selected["url"]).path)
    target = safe_join(target_dir, relative)
    if os.path.exists(target):
        return {"ok": False, "error": f"file already exists: {target}",
                "remediation": "Choose another destination or remove the file after review."}
    include_targets = []
    for rel in selected["include"]:
        try:
            include_target = _safe_include_target(target_dir, rel)
        except ToolError as exc:
            return {"ok": False, "error": str(exc)}
        if os.path.exists(include_target):
            return {"ok": False, "error": f"dependency already exists: {include_target}",
                    "remediation": "Remove the partial download or choose another destination."}
        include_targets.append((rel, include_target))
    total = (selected.get("size") or 0) + sum(
        (meta.get("size") or 0) for meta in selected["include"].values())
    if total > max_bytes:
        return {"ok": False, "error": f"asset needs {total} bytes, above limit {max_bytes}"}
    main = http_download(selected["url"], target, allowed_hosts=POLYHAVEN_HOSTS,
                         max_bytes=max_bytes, timeout=300)
    if not main.get("ok"):
        return main
    md5 = hashlib.md5()
    with open(target, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
    if selected.get("md5") and md5.hexdigest() != selected["md5"]:
        os.remove(target)
        return {"ok": False, "error": "downloaded file failed the provider MD5 check"}
    downloaded = [{"path": target, "bytes": main["bytes"], "sha256": main["sha256"],
                   "md5_verified": bool(selected.get("md5"))}]
    include_by_rel = {rel: target for rel, target in include_targets}
    for rel, meta in selected["include"].items():
        # Provider include paths were already validated under target_dir above.
        include_target = include_by_rel[rel]
        include_result = http_download(meta["url"], include_target,
                                       allowed_hosts=POLYHAVEN_HOSTS, max_bytes=max_bytes,
                                       timeout=300)
        if not include_result.get("ok"):
            return {"ok": False, "error": f"failed to download dependency {rel}",
                    "detail": include_result, "partial": downloaded}
        downloaded.append({"path": include_target, "bytes": include_result["bytes"],
                           "sha256": include_result["sha256"],
                           "md5_verified": bool(meta.get("md5"))})
    provenance = {
        "schema_version": 1,
        "asset_id": asset_id,
        "provider": "polyhaven",
        "provider_url": f"https://polyhaven.com/a/{asset_id}",
        "license": POLYHAVEN_LICENSE,
        "format": selected["format"],
        "resolution": selected["resolution"],
        "downloaded_at": now_iso(),
        "files": downloaded,
        "note": "CC0 asset. Attribution is not required but is good practice.",
    }
    write_json(os.path.join(target_dir, "provenance.json"), provenance)
    return {"ok": True, "asset_id": asset_id, "directory": target_dir,
            "main_file": target, "files": downloaded, "provenance": provenance}


def inspect_asset_license(provider: str, asset_id: str | None = None) -> dict:
    provider = (provider or "").lower()
    if provider == "polyhaven":
        if asset_id:
            response = http_request(f"{POLYHAVEN_API}/info/{urllib.parse.quote(asset_id)}",
                                    timeout=30, allowed_hosts=POLYHAVEN_HOSTS)
            if not response.get("ok"):
                return {"ok": False, "error": response.get("error") or "asset not found"}
            info = response.get("payload") or {}
            return {"ok": True, "provider": "polyhaven", "asset_id": asset_id,
                    "name": info.get("name"), "license": POLYHAVEN_LICENSE,
                    "authors": info.get("authors"), "source_url": f"https://polyhaven.com/a/{asset_id}"}
        return {"ok": True, "provider": "polyhaven", "license": POLYHAVEN_LICENSE,
                "evidence": "Provider-level license documented at polyhaven.com/license."}
    if provider == "sketchfab":
        return {"ok": False, "provider": "sketchfab",
                "error": "Per-asset license must be read from the specific asset; "
                         "search results include the API license field when available.",
                "manual_review_required": True}
    known = {p["id"] for p in PROVIDERS}
    if provider not in known:
        raise ToolError(f"unknown provider: {provider}")
    info = next(p for p in PROVIDERS if p["id"] == provider)
    return {"ok": False, "provider": provider, "license": info["license"],
            "manual_review_required": True,
            "reason": info.get("reason") or "No automated per-asset license lookup.",
            "source_url": PROVIDER_SITES.get(provider, "https://example.invalid")}


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
def _glb_info(path: str) -> dict:
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        header = handle.read(12)
        if len(header) < 12:
            raise ValueError("file is too small to be a GLB")
        magic, version, length = struct.unpack("<4sII", header)
        if magic != b"glTF":
            raise ValueError("missing glTF magic header")
        chunk_length, chunk_type = struct.unpack("<II", handle.read(8))
        if chunk_type != 0x4E4F534A:
            raise ValueError("first chunk is not JSON")
        json_bytes = handle.read(chunk_length)
    document = json.loads(json_bytes.decode("utf-8").rstrip("\x00 "))
    return _gltf_stats(document, base_dir=os.path.dirname(path), binary_length=size,
                       container="glb", declared_length=length)


def _gltf_stats(document: dict, *, base_dir: str, binary_length: int,
                container: str, declared_length: int | None = None) -> dict:
    issues, warnings = [], []
    accessors = document.get("accessors") or []
    meshes = document.get("meshes") or []
    triangle_count = 0
    primitive_count = 0
    primitives_with_uvs = 0
    for mesh in meshes:
        for primitive in mesh.get("primitives") or []:
            primitive_count += 1
            attributes = primitive.get("attributes") or {}
            if "TEXCOORD_0" in attributes:
                primitives_with_uvs += 1
            indices = primitive.get("indices")
            if indices is not None and indices < len(accessors):
                triangle_count += (accessors[indices].get("count") or 0) // 3
            else:
                position = attributes.get("POSITION")
                if position is not None and position < len(accessors):
                    triangle_count += (accessors[position].get("count") or 0) // 3
    missing = []
    for buffer in document.get("buffers") or []:
        uri = buffer.get("uri")
        if not uri:
            continue
        if uri.startswith("data:"):
            continue
        decoded = urllib.parse.unquote(uri)
        if os.path.isabs(decoded) or ".." in decoded.replace("\\", "/").split("/"):
            issues.append(f"unsafe buffer URI: {uri}")
            continue
        if not os.path.isfile(os.path.join(base_dir, decoded)):
            missing.append(decoded)
    images_external = 0
    for image in document.get("images") or []:
        uri = image.get("uri")
        if not uri or uri.startswith("data:"):
            continue
        images_external += 1
        decoded = urllib.parse.unquote(uri)
        if not os.path.isfile(os.path.join(base_dir, decoded)):
            missing.append(decoded)
    if missing:
        issues.append(f"missing external files: {sorted(set(missing))}")
    required = document.get("extensionsRequired") or []
    draco = "KHR_draco_mesh_compression" in required
    if draco:
        warnings.append("Draco-compressed geometry requires an engine importer that supports it")
    skins = document.get("skins") or []
    animations = document.get("animations") or []
    if not document.get("meshes"):
        issues.append("document contains no meshes")
    if triangle_count == 0:
        warnings.append("triangle count could not be derived from accessors")
    if primitive_count and primitives_with_uvs == 0:
        warnings.append("no primitive declares TEXCOORD_0 (UV) data")
    return {
        "container": container,
        "bytes": binary_length,
        "declared_length": declared_length,
        "asset": document.get("asset"),
        "scenes": len(document.get("scenes") or []),
        "nodes": len(document.get("nodes") or []),
        "meshes": len(meshes),
        "primitives": primitive_count,
        "primitives_with_uvs": primitives_with_uvs,
        "has_uvs": primitives_with_uvs > 0,
        "estimated_triangles": triangle_count,
        "materials": len(document.get("materials") or []),
        "images": len(document.get("images") or []),
        "external_images": images_external,
        "skins": len(skins),
        "joints": sum(len(s.get("joints") or []) for s in skins),
        "animations": [
            {"name": a.get("name") or f"animation_{i}", "channels": len(a.get("channels") or []),
             "samplers": len(a.get("samplers") or [])}
            for i, a in enumerate(animations)
        ],
        "extensions_required": required,
        "extensions_used": document.get("extensionsUsed") or [],
        "draco": draco,
        "issues": issues,
        "warnings": warnings,
        "has_rig": bool(skins),
        "has_animation": bool(animations),
    }


def _gltf_file_info(path: str) -> dict:
    document = read_json(path)
    base = os.path.dirname(path)
    return _gltf_stats(document, base_dir=base, binary_length=os.path.getsize(path), container="gltf")


def _obj_info(path: str) -> dict:
    vertices = faces = triangles = 0
    uv_count = normal_count = 0
    mtl = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("v "):
                vertices += 1
            elif line.startswith("vt "):
                uv_count += 1
            elif line.startswith("vn "):
                normal_count += 1
            elif line.startswith("f "):
                faces += 1
                # An n-gon triangulates into n-2 triangles.
                triangles += max(0, len(line.split()) - 3)
            elif line.startswith("mtllib "):
                mtl.append(line.split(None, 1)[1].strip())
    issues = []
    for name in mtl:
        if not os.path.isfile(os.path.join(os.path.dirname(path), name)):
            issues.append(f"missing material library: {name}")
    return {"container": "obj", "bytes": os.path.getsize(path), "vertices": vertices,
            "faces": faces, "triangles": triangles, "uv_count": uv_count,
            "normal_count": normal_count, "has_uvs": uv_count > 0,
            "has_normals": normal_count > 0,
            "material_libraries": mtl, "issues": issues,
            "warnings": ["OBJ face counts include polygons; triangulate before import."],
            "has_rig": False, "has_animation": False}


def _stl_info(path: str) -> dict:
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        head = handle.read(84)
    if head[:5].lower() == b"solid" and size % 84 != 0:
        return {"container": "stl", "bytes": size, "format": "ascii",
                "triangles": head.count(b"facet") or None}
    triangles = struct.unpack("<I", head[80:84])[0] if len(head) >= 84 else 0
    return {"container": "stl", "bytes": size, "format": "binary", "triangles": triangles}


def _image_info(path: str) -> dict:
    with open(path, "rb") as handle:
        head = handle.read(32)
    info = {"container": os.path.splitext(path)[1].lstrip(".").lower(),
            "bytes": os.path.getsize(path)}
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", head[16:24])
        info.update({"width": width, "height": height})
    elif head[:2] == b"\xff\xd8":
        info["format"] = "jpeg"
        info["note"] = "dimensions not parsed for JPEG"
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        info["format"] = "webp"
    else:
        info["warning"] = "unrecognised image header"
    return info


def validate_asset_file(path: str, *, max_triangles: int | None = None) -> dict:
    target = os.path.abspath(expand(path))
    if not os.path.isfile(target):
        raise ToolError(f"asset file not found: {target}")
    ext = os.path.splitext(target)[1].lower()
    issues, warnings = [], []
    try:
        if ext == ".glb":
            stats = _glb_info(target)
        elif ext == ".gltf":
            stats = _gltf_file_info(target)
        elif ext == ".obj":
            stats = _obj_info(target)
        elif ext == ".stl":
            stats = _stl_info(target)
        elif ext in (".png", ".jpg", ".jpeg", ".webp"):
            stats = _image_info(target)
        elif ext == ".fbx":
            with open(target, "rb") as handle:
                head = handle.read(64)
            stats = {"container": "fbx", "bytes": os.path.getsize(target),
                     "header_ok": head.startswith(b"Kaydara FBX Binary") or head.lstrip().startswith(b"; FBX"),
                     "warnings": ["FBX internals are not parsed here; verify in Blender or the engine."]}
        elif ext == ".blend":
            stats = {"container": "blend", "bytes": os.path.getsize(target),
                     "warnings": ["Use blender_validate for full .blend validation."]}
        else:
            stats = {"container": ext.lstrip("."), "bytes": os.path.getsize(target),
                     "warnings": ["No structural parser for this format."]}
    except (OSError, ValueError, json.JSONDecodeError, struct.error) as exc:
        return {"ok": False, "path": target, "error": f"invalid asset: {exc}"}
    issues += stats.pop("issues", []) or []
    warnings += stats.pop("warnings", []) or []
    triangles = stats.get("estimated_triangles") or stats.get("triangles")
    if max_triangles and triangles and triangles > max_triangles:
        warnings.append(f"triangle budget exceeded: {triangles} > {max_triangles}")
    stats["sha256"] = sha256_file(target)
    stats["size_human"] = f"{os.path.getsize(target):,} bytes"
    return {"ok": not issues, "path": target, "format": ext.lstrip("."),
            "issues": issues, "warnings": warnings, "stats": stats}


def asset_manifest(paths: list[str], destination: str | None = None) -> dict:
    """Create a provenance/validation manifest for files already on disk."""
    records = []
    for path in paths:
        record = validate_asset_file(path)
        records.append(record)
    manifest = {"schema_version": 1, "created_at": now_iso(),
                "assets": records,
                "note": "Files with unknown licenses must not be shipped; add source and "
                        "license fields after reviewing the provider's terms."}
    if destination:
        write_json(os.path.abspath(expand(destination)), manifest)
        manifest["written_to"] = os.path.abspath(expand(destination))
    return manifest
