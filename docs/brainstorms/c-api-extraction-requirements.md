---
date: 2026-04-16
topic: c-api-extraction
---

# C API Extraction Support for kit-api-extract Skill

## Problem Frame

The `kit-api-extract` skill currently only supports JS API extraction from `.d.ts`/`.d.ets` declaration files. HarmonyOS/OpenHarmony also exposes C APIs through `.h` header files in `interface_sdk_c`, which are not covered. Users who need to audit both JS and C APIs must run separate workflows manually. C API declarations have a much more structured and regular format (Doxygen comments with `@kit`, `@library`, `@syscap`, etc.), making them amenable to scripted extraction rather than relying heavily on Agent exploration.

## Requirements

**C API Declaration Extraction**

- R1. Extend the existing `extract_kit_api.py` (which already contains `parse_c_file()` at lines 477-539 and `scan_c_sdk()` at lines 609-611) to extract `@library` metadata (currently missing) and add `api_type: "c"` field to C API records. Also add `api_type: "js"` to JS API records for consistency.
- R2. `module_name` for C APIs is derived from the file path (e.g., `CryptoArchitectureKit/crypto_digest.h` → `CryptoArchitectureKit.crypto_digest`), replacing the current `file_path.name` approach.
- R3. Function declarations are identified by `OH_*` and `OHOS_*` prefix patterns and standard C function signature format.

**Script-Based Implementation Mapping**

- R4. New script `extract_c_impl_map.py` maps C API declarations to implementation files using deterministic methods (reusing `parse_build_gn()` from existing `extract_component_map.py` where applicable):
  - `@library` tag → library `.so` name
  - Search `databases_dir` for BUILD.gn files that build that library
  - Extract source file lists from matched BUILD.gn targets
  - Match function names (`OH_*`/`OHOS_*`) to `.cpp`/`.c` source files via string search, preferring implementation files over headers and excluding test directories
- R5. The script directly fills `impl_repo_path` and `impl_file_path` fields. `NAPI_map_file` and `impl_api_name` are left empty for C APIs (no NAPI layer). `Framework_decl_file` is filled when discoverable, empty otherwise.

**Unified Workflow**

- R6. SKILL.md accepts a new optional parameter `c_sdk_path`. The skill runs JS extraction, C extraction, or both based on which paths are provided.
- R7. When both JS and C SDK paths are provided, both `api.jsonl` outputs are merged into a single file with `api_type` field distinguishing JS (`"js"`) vs C (`"c"`) records.
- R8. Downstream processing (Phase 3 agent exploration, Phase 4 merge, Phase 5 retry, Phase 6 report) applies to both API types. C APIs use a simplified agent prompt that skips NAPI search.
- R9. For C APIs, agent exploration (a C-specific sub-phase of Phase 3) is only dispatched for APIs where the scripted mapping did not achieve sufficient coverage. The C API agent prompt skips NAPI layer search (Steps 2-3 of the existing template) and focuses on tracing from `.h` declaration to implementation.

**Output Compatibility**

- R10. Final `impl_api.jsonl` uses the same 9-field schema plus `api_type` field (10 fields total) for both JS and C APIs. C API records have empty `NAPI_map_file` and `impl_api_name`. Phase 5 retry logic must exclude C API records from NAPI coverage checks. Downstream skills (`api-level-scan`, etc.) need `api_type`-aware branching to skip NAPI-specific analysis for C APIs.

## Success Criteria

- C API declarations are extracted from `.h` files with the same reliability as JS API declarations from `.d.ts` files.
- Scripted mapping achieves >= 60% coverage for `impl_file_path` on C APIs without agent involvement.
- Combined JS + C extraction run produces a single valid `impl_api.jsonl` consumable by existing downstream skills.
- The existing JS-only workflow is unchanged when `c_sdk_path` is not provided.

## Scope Boundaries

- Not changing the existing JS API extraction pipeline — it continues to work identically.
- Not creating a new standalone skill — this is an extension of `kit-api-extract`.
- Not modifying downstream skills (`api-level-scan`, etc.) beyond adding `api_type`-aware branching for NAPI skip logic. The core audit rules and output format remain unchanged.
- Not handling C API types beyond function declarations (enums, structs, typedefs are excluded from the API list, same as JS container types).

## Key Decisions

- **Unified output format over separate pipelines**: Merging into one `api.jsonl`/`impl_api.jsonl` with `api_type` field minimizes downstream changes and simplifies the user workflow.
- **Maximize scripting for C APIs**: C API structure (`@library`, BUILD.gn, function naming conventions) is regular enough for deterministic extraction. Agent exploration is a fallback, not the primary mechanism.
- **`module_name` from file path**: C APIs lack the `@ohos.xxx` module naming convention; deriving from file path provides a stable, predictable identifier.
- **Empty NAPI fields**: C APIs have no NAPI layer; leaving those fields empty rather than omitting them maintains schema consistency.

## Dependencies / Assumptions

- C SDK directory structure follows the observed pattern: Kit-named or subsystem-named directories containing `.h` files with Doxygen `@kit` tags.
- `@library` tags accurately reflect the `.so` binary built by component repos in `databases_dir`.
- The `c_file_kit_sub_system.json` mapping file in `interface_sdk_c` is available and up-to-date for Kit assignment fallback.
- Component repos in `databases_dir` contain BUILD.gn files with `ohos_shared_library` targets that can be matched to `@library` names.

## Outstanding Questions

### Deferred to Planning

- [Affects R4][Needs research] How reliably does `@library` tag value map to BUILD.gn target names in component repos? The mapping convention (e.g., `libohcrypto.so` → which BUILD.gn target?) needs validation against actual repo structure.
- [Affects R4][Technical] Should `extract_c_impl_map.py` also leverage `.ndk.json` symbol lists for validation, or rely solely on `@library` + BUILD.gn + function name matching?
- [Affects R8][Technical] What is the exact coverage threshold below which agent fallback triggers for C APIs? (JS uses 90% for Phase 5 retry; C may warrant a different threshold.)

## Next Steps

-> `/ce:plan` for structured implementation planning. Most blocking decisions are resolved; the key uncertainty around `@library` → BUILD.gn mapping reliability (affects R4) will be validated during planning before committing to the scripted approach.
