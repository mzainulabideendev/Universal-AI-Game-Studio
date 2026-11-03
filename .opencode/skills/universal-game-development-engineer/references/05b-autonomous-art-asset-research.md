# Autonomous Art, Asset Research and Production Module

Use this reference when a project needs a complete production-ready game brief,
art direction, internet asset research, licensing review and asset provenance
records before content is committed to a build.

## 1. UNIVERSAL PURPOSE
Extend the existing Universal Game Development Engineer into a reusable system
for developers, artists, students, indie studios and professional teams.

The system must work with different users, computers, project folders, game
engines, genres, art styles and target platforms.

Never hardcode one developer's name, computer paths, installed engines, preferred
genre, visual style or assets into the reusable skill.

Discover the current user's environment and requirements at runtime.

Integrate this module into the existing skill and MCP workflow. Preserve existing
functionality and configuration.

## 2. PROMPT-TO-GAME UNDERSTANDING
When a user describes a game, interpret the request as a complete
game-production brief.

Extract:

- Genre and subgenre.
- 2D, 2.5D or 3D presentation.
- Core gameplay loop.
- Player character and controls.
- Camera and movement style.
- World setting.
- Visual style and artistic direction.
- Required environments and levels.
- Characters, enemies and NPCs.
- Gameplay mechanics and progression.
- UI, menus and HUD.
- Sound and music requirements.
- Target platform and performance goals.
- Multiplayer or online requirements.
- Budget and asset-license preferences.
- Existing project and available resources.
Separate explicit user requirements from inferred design decisions.

If an essential decision is missing, ask a concise question. Otherwise, propose
sensible professional defaults, document them and continue.

Do not force every user through a long questionnaire.

Create a concise Game Design Document, an asset requirement list, a technical
implementation plan and a milestone plan.

The design must be specific to the requested game, not a generic collection of
unrelated features.

## 3. AUTONOMOUS AI GAME ART DIRECTOR
Act as a professional Art Director and Environment Designer.

When the user does not prescribe a visual style, independently propose a suitable
art direction based on the genre, audience, gameplay readability, platform,
available assets and budget.

Possible directions include:

- Realistic cinematic.
- Stylized realism.
- Fantasy.
- Science fiction.
- Low-poly.
- Retro or pixel art.
- Cartoon.
- Horror.
- Survival.
- Historical.
- Minimalist.
- Hand-painted.
- Other styles appropriate to the concept.
Do not automatically choose realistic graphics for every game.

Create an art-direction specification containing:

1. Visual identity and mood.
2. Color palette.
3. Lighting and contrast.
4. Materials and surface treatment.
5. Character and creature design.
6. Environment design.
7. Camera composition.
8. Animation style.
9. UI visual language.
10. Audio atmosphere.
11. Performance-aware rendering choices.
For major projects, create a small visual target or representative vertical slice
before producing large amounts of content.

If image generation is available, use it for authorized concept art, original
textures, UI concepts or other appropriate image assets. Generated concept art
must not be presented as a functional 3D model, rig or animation.

When concept art is useful, generate it as a reference for implementation, then
create or acquire the actual required game assets.

The AI Art Director may make creative decisions independently, but must respect
explicit user requirements, accessibility, licensing and technical constraints.

Document important creative decisions so that other agents and contributors can
follow the same art direction.

## 4. REAL INTERNET ASSET RESEARCH
Before creating every asset from scratch, investigate whether a suitable, legally
usable asset already exists.

Search the internet for assets relevant to the actual game requirements.

Potential categories include:

- 3D characters and creatures.
- Static and skeletal meshes.
- Animation packs.
- Environments and modular environment kits.
- Terrain and foliage.
- Rocks, trees, buildings and props.
- PBR materials and textures.
- HDRIs and sky resources.
- 2D sprites and tilesets.
- UI icons and interface resources.
- Sound effects and ambient recordings.
- Music.
- Fonts.
- Particles and visual effects.
- Shaders and engine plugins.
- Sample projects and technical references.
Discover which internet-search, browser, asset-catalogue and download tools are
actually available.

Use official websites, documented APIs, legitimate public asset repositories and
authorized download mechanisms.

Do not assume that a browser tool, internet connection, API key or download
permission exists.

If one source cannot be searched or downloaded, try another appropriate source.

### Candidate sources
Evaluate relevant sources rather than blindly downloading from every website.

Examples include:

- Poly Haven for CC0 3D assets, textures and HDRIs.
- Kenney for game assets under the licenses specified for its asset packs.
- BlenderKit and Blender's supported asset workflows.
- Unity Asset Store for Unity-compatible licensed content.
- Fab for applicable game-development assets.
- Sketchfab for models with individually verified licensing.
- OpenGameArt for assets with individually checked licenses.
- Freesound for audio with individually checked licenses.
- Official engine sample projects and documentation.
- Other reputable repositories that match the requested asset type.
These are candidate sources, not a guarantee that every asset is free, suitable,
downloadable or redistributable.

Never bypass account requirements, paywalls, CAPTCHAs, access restrictions or
download limitations.

Do not use unauthorized scraping when a source prohibits it.

## 5. ASSET SEARCH AND RANKING ENGINE
Translate the game design into structured asset searches.

For each required asset, determine:

- Asset category.
- Intended gameplay purpose.
- Visual style.
- Required format.
- Engine compatibility.
- Polygon and texture budget.
- Required rig or skeleton.
- Required animation clips.
- Material requirements.
- Scale and orientation.
- Collision requirements.
- Licensing requirements.
- Whether modification is allowed.
- Whether commercial use and redistribution are permitted.
Search using several relevant terms when necessary.

Evaluate candidate assets against:

1. Visual suitability.
2. Technical compatibility.
3. License compatibility.
4. Completeness of required files.
5. Quality and consistency.
6. Animation and rig requirements.
7. Performance cost.
8. Download reliability.
9. Integration effort.
10. Consistency with the rest of the game.
Return the best suitable candidates rather than simply selecting the first search
result.

When the user has not explicitly approved a paid asset or budget, prefer suitable
free and legally usable options.

If no suitable free asset exists, explain the gap and offer alternatives such as
original procedural creation, an available compatible asset or an optional paid
asset requiring approval.

Do not silently purchase assets.

## 6. LICENSING AND ASSET PROVENANCE
Create an asset provenance manifest for every external asset used.

Record, where available:

- Asset name.
- Original creator.
- Source page.
- Download location.
- License identifier.
- License text or a reference to the applicable terms.
- Attribution requirements.
- Commercial-use conditions.
- Modification restrictions.
- Redistribution restrictions.
- Required notices.
- Date checked.
- File hash when practical.
- Actual project destination.
Use the license applicable to the exact asset and its dependencies.

Distinguish CC0, permissive open licenses, attribution-required licenses,
noncommercial licenses, share-alike licenses, proprietary licenses and unknown
licenses.

Do not treat a search snippet or a website's general reputation as sufficient
evidence for every asset's license.

Do not use assets with unresolved licensing when the requested distribution
requires clear rights.

If an asset's licensing is unclear, quarantine it from the final build until the
issue is resolved.

For commercial distribution, preserve the required notices and attributions.

Do not redistribute standalone asset libraries when the license only permits
restricted reuse, or when the installed assets require a different downstream
licence than the final game distribution.

This module should be used together with the production pipeline and the engine
selection guidance so that art direction, asset sourcing and technical delivery
remain technically valid, legally compliant and consistent with the target game.
