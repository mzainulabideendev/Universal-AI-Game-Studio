"""Honest research catalogue for free image, texture and 3D generation.

Nothing here generates an asset, downloads a model, installs software or calls a
service. Each candidate is classified by what its own documentation supports and
by whether the route is actually free. Marketing claims are not treated as proof.

Classification
--------------
``free_hosted_api``              Documented free API with no payment requirement.
``free_limited_hosted_service``  Free but rate/time limited or best-effort.
``open_source_local``            Local software/model; this project will not install it.
``paid_service``                 Paid; refused under free-only mode.
``research_only``                Research code or no usable hosted API.
"""

from __future__ import annotations

SCHEMA_VERSION = 1
VERIFICATION_DATE = "2026-11-10"

FREE_HOSTED_API = "free_hosted_api"
FREE_LIMITED_HOSTED = "free_limited_hosted_service"
OPEN_SOURCE_LOCAL = "open_source_local"
PAID_SERVICE = "paid_service"
RESEARCH_ONLY = "research_only"

CATEGORIES = (FREE_HOSTED_API, FREE_LIMITED_HOSTED, OPEN_SOURCE_LOCAL,
              PAID_SERVICE, RESEARCH_ONLY)

CAPABILITIES = (
    "text_to_image", "image_to_image", "texture_generation",
    "seamless_material_generation", "normal_map_generation",
    "roughness_map_generation", "text_to_3d", "image_to_3d",
    "animation_generation",
)

CANDIDATES: list[dict] = [
    {
        "id": "pollinations_classic",
        "name": "Pollinations (Classic image API)",
        "category": FREE_HOSTED_API,
        "official_source": ("https://github.com/pollinations/pollinations/blob/"
                            "master/APIDOCS.md"),
        "verified_on": VERIFICATION_DATE,
        "api_available": True,
        "free_tier_limits": ("No signup documented; approximately one image per 45 "
                             "seconds; one model; best-effort with no uptime guarantee."),
        "capabilities": {"text_to_image": True, "image_to_image": False,
                         "texture_generation": False,
                         "seamless_material_generation": False,
                         "normal_map_generation": False,
                         "roughness_map_generation": False,
                         "text_to_3d": False, "image_to_3d": False,
                         "animation_generation": False},
        "license": "See the current Pollinations project terms; not assumed here.",
        "commercial_use": "Unverified; review the current terms before commercial use.",
        "attribution_required": "Unverified.",
        "watermark": "JPEG output includes a small logo according to the API docs.",
        "rate_limits": "About one request per 45 seconds.",
        "hardware_requirements": "None locally (hosted).",
        "output_formats": ["JPEG"],
        "quality_limitations": ["Single model; not suitable for production texture sets.",
                                "No texture maps, normal maps, roughness maps or meshes."],
        "data_handling": "Requests leave the machine; review the provider policy.",
        "requires_payment_info": False,
        "notes": ["Suitable only as a labelled concept-image experiment."],
    },
    {
        "id": "stability_api",
        "name": "Stability AI API",
        "category": PAID_SERVICE,
        "official_source": "https://platform.stability.ai/pricing",
        "verified_on": VERIFICATION_DATE,
        "api_available": True,
        "free_tier_limits": "25 trial credits (1 credit = $0.01), then paid.",
        "capabilities": {"text_to_image": True, "image_to_image": True,
                         "texture_generation": True,
                         "seamless_material_generation": True,
                         "normal_map_generation": False,
                         "roughness_map_generation": False,
                         "text_to_3d": True, "image_to_3d": True,
                         "animation_generation": False},
        "license": "Stability AI API terms; model licences vary.",
        "commercial_use": "Permitted only under the paid API terms.",
        "attribution_required": "Per the current API terms.",
        "watermark": "Per the current API terms.",
        "rate_limits": "Account/credit dependent.",
        "hardware_requirements": "None locally (hosted).",
        "output_formats": ["PNG", "JPEG", "GLB", "other per model"],
        "quality_limitations": ["Trial credit is not an ongoing free allowance."],
        "data_handling": "Hosted request; review the data policy.",
        "requires_payment_info": True,
        "notes": ["Classified trial_only in the provider policy; refused by free-only mode."],
    },
    {
        "id": "huggingface_inference",
        "name": "Hugging Face Inference Providers",
        "category": PAID_SERVICE,
        "official_source": "https://huggingface.co/docs/api-inference/pricing",
        "verified_on": VERIFICATION_DATE,
        "api_available": True,
        "free_tier_limits": "Free accounts receive no monthly credits; purchase required.",
        "capabilities": {"text_to_image": True, "image_to_image": True,
                         "texture_generation": "unknown",
                         "seamless_material_generation": "unknown",
                         "normal_map_generation": "unknown",
                         "roughness_map_generation": "unknown",
                         "text_to_3d": "unknown", "image_to_3d": "unknown",
                         "animation_generation": "unknown"},
        "license": "Depends on the selected model.",
        "commercial_use": "Depends on the selected model and provider.",
        "attribution_required": "Depends on the model licence.",
        "watermark": "Depends on the model.",
        "rate_limits": "Provider/account dependent.",
        "hardware_requirements": "None locally (hosted).",
        "output_formats": ["Depends on model"],
        "quality_limitations": ["Paid inference, so it does not satisfy free-only mode."],
        "data_handling": "Hosted request; review provider policy.",
        "requires_payment_info": True,
        "notes": ["Included to show that a familiar brand is not a free allowance."],
    },
    {
        "id": "stable_diffusion_local",
        "name": "Stable Diffusion (local, via ComfyUI or a compatible runtime)",
        "category": OPEN_SOURCE_LOCAL,
        "official_source": "https://github.com/CompVis/stable-diffusion",
        "verified_on": VERIFICATION_DATE,
        "api_available": False,
        "free_tier_limits": ("No hosted free API. Runs locally after the user installs a "
                             "runtime and obtains model weights."),
        "capabilities": {"text_to_image": True, "image_to_image": True,
                         "texture_generation": True,
                         "seamless_material_generation": True,
                         "normal_map_generation": "unknown",
                         "roughness_map_generation": "unknown",
                         "text_to_3d": False, "image_to_3d": False,
                         "animation_generation": "unknown"},
        "license": "CreativeML Open RAIL-M (model); runtime licences differ.",
        "commercial_use": ("Permitted by the RAIL-M licence subject to its use "
                           "restrictions; verify the exact model card."),
        "attribution_required": "Per the model card and runtime licence.",
        "watermark": "No mandatory watermark in the base model.",
        "rate_limits": "None hosted; limited by local hardware.",
        "hardware_requirements": ("A dedicated GPU with sufficient VRAM is typically "
                                  "needed; the documented 16 GB / integrated-GPU machine "
                                  "may not be practical. Not measured here."),
        "output_formats": ["PNG", "JPEG"],
        "quality_limitations": ["Seamless material output requires additional setup and "
                                "validation; not demonstrated by this project."],
        "data_handling": "Local; prompts and images stay on the machine.",
        "requires_payment_info": False,
        "notes": ["Not installed. No model weights were downloaded.",
                  "Procedural Blender output must never be labelled AI-generated."],
    },
    {
        "id": "comfyui_local",
        "name": "ComfyUI",
        "category": OPEN_SOURCE_LOCAL,
        "official_source": "https://github.com/comfyanonymous/ComfyUI",
        "verified_on": VERIFICATION_DATE,
        "api_available": False,
        "free_tier_limits": "Local runtime; no hosted free allowance.",
        "capabilities": {"text_to_image": True, "image_to_image": True,
                         "texture_generation": True,
                         "seamless_material_generation": True,
                         "normal_map_generation": "unknown",
                         "roughness_map_generation": "unknown",
                         "text_to_3d": False, "image_to_3d": False,
                         "animation_generation": "unknown"},
        "license": "GPL-3.0 (verify the repository).",
        "commercial_use": "Follow the runtime and model licences.",
        "attribution_required": "Per the runtime and model licences.",
        "watermark": "None by default.",
        "rate_limits": "Local hardware only.",
        "hardware_requirements": "GPU/VRAM dependent; not validated on this machine.",
        "output_formats": ["PNG", "JPEG", "other via nodes"],
        "quality_limitations": ["Requires manual workflow authoring and validation."],
        "data_handling": "Local.",
        "requires_payment_info": False,
        "notes": ["Not installed. This project does not download models."],
    },
    {
        "id": "triposr_local",
        "name": "TripoSR (image-to-3D)",
        "category": OPEN_SOURCE_LOCAL,
        "official_source": "https://github.com/VAST-AI-Research/TripoSR",
        "verified_on": VERIFICATION_DATE,
        "api_available": False,
        "free_tier_limits": "Local model; no hosted free API.",
        "capabilities": {"text_to_image": False, "image_to_image": False,
                         "texture_generation": False,
                         "seamless_material_generation": False,
                         "normal_map_generation": False,
                         "roughness_map_generation": False,
                         "text_to_3d": False, "image_to_3d": True,
                         "animation_generation": False},
        "license": "MIT (verify the repository before redistribution).",
        "commercial_use": "Permitted by the MIT licence; model weights may carry "
                          "additional terms.",
        "attribution_required": "MIT copyright notice.",
        "watermark": "None stated.",
        "rate_limits": "Local hardware only.",
        "hardware_requirements": "GPU recommended; not validated on this machine.",
        "output_formats": ["OBJ", "GLB (via export)"],
        "quality_limitations": ["Single-image reconstruction quality varies; no rig or "
                                "animation."],
        "data_handling": "Local.",
        "requires_payment_info": False,
        "notes": ["Not installed. No weights were downloaded."],
    },
    {
        "id": "tripo_api",
        "name": "Tripo API",
        "category": PAID_SERVICE,
        "official_source": "https://platform.tripo3d.ai/docs/pricing",
        "verified_on": VERIFICATION_DATE,
        "api_available": True,
        "free_tier_limits": "Usage-based paid credits; no ongoing free API allowance.",
        "capabilities": dict.fromkeys(CAPABILITIES, "unknown") | {
            "text_to_3d": True, "image_to_3d": True},
        "license": "Tripo API terms.",
        "commercial_use": "Per paid API terms.",
        "attribution_required": "Per paid API terms.",
        "watermark": "Per paid API terms.",
        "rate_limits": "Credit/account dependent.",
        "hardware_requirements": "None locally (hosted).",
        "output_formats": ["GLB", "FBX", "OBJ", "USDZ"],
        "quality_limitations": ["Paid."],
        "data_handling": "Hosted request.",
        "requires_payment_info": True,
        "notes": ["The open-source TripoSR route is separate and local."],
    },
    {
        "id": "meshy_api",
        "name": "Meshy API",
        "category": PAID_SERVICE,
        "official_source": "https://docs.meshy.ai/en/api/pricing",
        "verified_on": VERIFICATION_DATE,
        "api_available": True,
        "free_tier_limits": "Prepaid credits; no ongoing free API allowance.",
        "capabilities": dict.fromkeys(CAPABILITIES, "unknown") | {
            "text_to_3d": True, "image_to_3d": True},
        "license": "Meshy API terms.",
        "commercial_use": "Per paid API terms.",
        "attribution_required": "Per paid API terms.",
        "watermark": "Per paid API terms.",
        "rate_limits": "Credit/account dependent.",
        "hardware_requirements": "None locally (hosted).",
        "output_formats": ["GLB", "FBX", "OBJ", "USDZ"],
        "quality_limitations": ["Paid."],
        "data_handling": "Hosted request.",
        "requires_payment_info": True,
        "notes": ["Existing Phase 1-5 Meshy integration remains paid and gated."],
    },
    {
        "id": "free_hosted_3d",
        "name": "Free hosted text-to-3D API",
        "category": RESEARCH_ONLY,
        "official_source": "No provider with a documented ongoing free API was verified.",
        "verified_on": VERIFICATION_DATE,
        "api_available": False,
        "free_tier_limits": "Not established.",
        "capabilities": dict.fromkeys(CAPABILITIES, "unknown"),
        "license": "Not applicable.",
        "commercial_use": "Not applicable.",
        "attribution_required": "Not applicable.",
        "watermark": "Not applicable.",
        "rate_limits": "Not applicable.",
        "hardware_requirements": "Not applicable.",
        "output_formats": [],
        "quality_limitations": ["No verified free hosted route exists in this research."],
        "data_handling": "Not applicable.",
        "requires_payment_info": "unknown",
        "notes": ["Do not integrate a 3D provider until API, licensing and cost are clear."],
    },
]


def _by_category() -> dict:
    grouped = {category: [] for category in CATEGORIES}
    for candidate in CANDIDATES:
        grouped[candidate["category"]].append(candidate["id"])
    return grouped


def catalog() -> dict:
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "verification_date": VERIFICATION_DATE,
        "categories": {
            FREE_HOSTED_API: "Documented free hosted API.",
            FREE_LIMITED_HOSTED: "Free but limited/best-effort hosted service.",
            OPEN_SOURCE_LOCAL: "Local open-source software; not installed here.",
            PAID_SERVICE: "Paid service; refused under free-only mode.",
            RESEARCH_ONLY: "Research-only or no usable hosted route.",
        },
        "by_category": _by_category(),
        "candidates": CANDIDATES,
        "asset_downloads": 0,
        "model_downloads": 0,
        "installs": 0,
        "network_calls": 0,
        "note": ("Research catalogue only. No image, texture or 3D asset was generated, "
                 "downloaded or installed."),
    }


def capabilities() -> dict:
    """Summarise capability availability honestly across the research set."""
    summary = {}
    for capability in CAPABILITIES:
        free_hosted = []
        local = []
        paid = []
        for candidate in CANDIDATES:
            value = (candidate.get("capabilities") or {}).get(capability)
            if value is True:
                if candidate["category"] in (FREE_HOSTED_API, FREE_LIMITED_HOSTED):
                    free_hosted.append(candidate["id"])
                elif candidate["category"] == OPEN_SOURCE_LOCAL:
                    local.append(candidate["id"])
                elif candidate["category"] == PAID_SERVICE:
                    paid.append(candidate["id"])
        summary[capability] = {
            "free_hosted_api": free_hosted,
            "open_source_local": local,
            "paid_service": paid,
            "available_now": False,
            "reason": ("No provider is configured or authorized and no local model is "
                       "installed; this project did not generate or download an asset."),
        }
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "verification_date": VERIFICATION_DATE,
        "capabilities": summary,
        "verified_free_hosted_available_now": [],
        "installed_local_generators": [],
        "asset_generation_performed": False,
        "procedural_blender_is_not_ai": True,
        "note": ("Free hosted text-to-image exists only as a rate-limited concept-image "
                 "route. No verified free hosted texture, normal-map, roughness-map or "
                 "3D-mesh API was established. Local open-source routes require separate "
                 "installation and licensing review."),
    }


def find(capability: str) -> dict:
    name = (capability or "").strip().lower()
    if name not in CAPABILITIES:
        raise ValueError(f"unknown asset capability {capability!r}; expected {list(CAPABILITIES)}")
    report = capabilities()
    return {"ok": True, "capability": name,
            "result": report["capabilities"][name], "network_calls": 0,
            "note": report["note"]}
