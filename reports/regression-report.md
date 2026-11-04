# Regression report

Generated: 2026-11-04T16:53:22Z

## Summary

- Tests ran: 100
- Passed: 100
- Failed: 0
- Errors: 0
- Skipped: 0
- Duration: 8.82s
- Regression status: **passed**

## Environment

- Platform: Windows-11-10.0.26200-SP0
- Python: 3.12.10
- Tools registered: 77
- Blender detected: True
- Meshy key configured: False
- LLM provider: openai (key configured: False, live verified: false)

## Results

| Test | Result | ms | Failure |
| --- | --- | --- | --- |
| `test_game_studio.AssetAndAnimationTests.test_glb_rig_inspection` | passed | 8 |  |
| `test_game_studio.AssetAndAnimationTests.test_manual_only_provider_is_not_simulated` | passed | 2 |  |
| `test_game_studio.AssetAndAnimationTests.test_obj_validation_counts_triangles_and_uvs` | passed | 5 |  |
| `test_game_studio.AssetAndAnimationTests.test_retarget_requires_matching_skeletons` | passed | 7 |  |
| `test_game_studio.AssetAndAnimationTests.test_unrigged_glb_is_reported_not_crashed` | passed | 4 |  |
| `test_game_studio.BlenderBlockoutTests.test_render_only_uses_and_removes_temporary_blend` | passed | 4 |  |
| `test_game_studio.DetectAndProjectTests.test_discover_project_by_marker` | passed | 7 |  |
| `test_game_studio.DetectAndProjectTests.test_unity_project_inspection` | passed | 76 |  |
| `test_game_studio.DetectAndProjectTests.test_unknown_project_reports_expectations` | passed | 2 |  |
| `test_game_studio.EngineStagingTests.test_engine_build_requires_confirmation_and_arguments` | passed | 6 |  |
| `test_game_studio.EngineStagingTests.test_stage_and_verify_unity_asset` | passed | 30 |  |
| `test_game_studio.EngineStagingTests.test_stage_rejects_engine_mismatch` | passed | 7 |  |
| `test_game_studio.EngineStagingTests.test_stage_requires_confirmation_and_respects_overwrite` | passed | 19 |  |
| `test_game_studio.EngineStagingTests.test_unreal_automation_is_reported_as_staged_only` | passed | 8 |  |
| `test_game_studio.MeshyGuardTests.test_animation_library_reports_missing_key_without_network` | passed | 1 |  |
| `test_game_studio.MeshyGuardTests.test_balance_without_key_is_not_configured` | passed | 2 |  |
| `test_game_studio.MeshyGuardTests.test_generation_requires_explicit_confirmation` | passed | 1 |  |
| `test_game_studio.MeshyKeyTests.test_configure_rejected_key_is_not_saved` | passed | 1 |  |
| `test_game_studio.MeshyKeyTests.test_configure_rejects_control_characters_before_network` | passed | 2 |  |
| `test_game_studio.MeshyKeyTests.test_configure_requires_confirmation` | passed | 1 |  |
| `test_game_studio.MeshyKeyTests.test_configure_validates_then_saves_without_returning_key` | passed | 14 |  |
| `test_game_studio.MeshyKeyTests.test_environment_variable_overrides_local_file` | passed | 4 |  |
| `test_game_studio.MeshyKeyTests.test_local_key_is_used_by_balance` | passed | 13 |  |
| `test_game_studio.MeshyKeyTests.test_provider_state_reflects_local_key` | passed | 10 |  |
| `test_game_studio.MeshyKeyTests.test_save_load_and_clear_local_key` | passed | 6 |  |
| `test_game_studio.MeshyKeyTests.test_setup_guide_has_real_steps_and_status` | passed | 2 |  |
| `test_game_studio.ProjectMemoryTests.test_comparison_flags_a_tampered_verified_claim` | passed | 103 |  |
| `test_game_studio.ProjectMemoryTests.test_manifest_refuses_credential_like_values` | passed | 32 |  |
| `test_game_studio.ProjectMemoryTests.test_manifest_requires_confirmation_and_is_project_local` | passed | 18 |  |
| `test_game_studio.ProjectMemoryTests.test_manifest_survives_reload_with_statuses_and_decisions` | passed | 81 |  |
| `test_game_studio.ProjectMemoryTests.test_status_guards_reject_unsupported_claims` | passed | 30 |  |
| `test_game_studio.ServerProtocolTests.test_initialize_and_ping` | passed | 2 |  |
| `test_game_studio.ServerProtocolTests.test_tool_error_is_clean_json` | passed | 1 |  |
| `test_game_studio.ServerProtocolTests.test_tools_list_is_unique_and_has_handlers` | passed | 1 |  |
| `test_game_studio.ServerProtocolTests.test_unknown_tool_returns_tool_error` | passed | 1 |  |
| `test_game_studio.SpecificationTests.test_acceptance_tests_cover_explicit_requirements` | passed | 7 |  |
| `test_game_studio.SpecificationTests.test_dependency_graph_is_acyclic_and_ordered` | passed | 7 |  |
| `test_game_studio.SpecificationTests.test_non_humanoid_character_gets_a_compatible_rig` | passed | 5 |  |
| `test_game_studio.SpecificationTests.test_requested_but_missing_engine_is_reported` | passed | 3 |  |
| `test_game_studio.SpecificationTests.test_spec_separates_explicit_from_assumptions` | passed | 6 |  |
| `test_game_studio.UnderstandingTests.test_exclusion_is_not_turned_into_a_requirement` | passed | 4 |  |
| `test_game_studio.UnderstandingTests.test_multiple_engines_and_style_conflict_are_reported` | passed | 6 |  |
| `test_game_studio.UnderstandingTests.test_questions_are_material_and_bounded` | passed | 4 |  |
| `test_game_studio.UnderstandingTests.test_roman_urdu_request_is_understood_and_traceable` | passed | 6 |  |
| `test_game_studio.UnderstandingToolsTests.test_analyze_tool_is_read_only_and_returns_classification` | passed | 7 |  |
| `test_game_studio.UnderstandingToolsTests.test_new_tools_are_registered` | passed | 1 |  |
| `test_game_studio.UnderstandingToolsTests.test_spec_and_manifest_tools_round_trip` | passed | 28 |  |
| `test_game_studio.UtilTests.test_config_is_written_outside_repo_and_audit_reads` | passed | 22 |  |
| `test_game_studio.UtilTests.test_config_rejects_unknown_key` | passed | 3 |  |
| `test_game_studio.UtilTests.test_safe_join_blocks_traversal_and_absolute_paths` | passed | 2 |  |
| `test_p0_v4.GovernanceTests.test_ask_permission_requires_confirm` | passed | 3 |  |
| `test_p0_v4.GovernanceTests.test_autonomous_mode_does_not_bypass_paid_approval` | passed | 13 |  |
| `test_p0_v4.GovernanceTests.test_default_mode_is_guided_least_privilege` | passed | 3 |  |
| `test_p0_v4.GovernanceTests.test_deny_wins_even_in_autonomous_mode` | passed | 15 |  |
| `test_p0_v4.GovernanceTests.test_mandatory_approval_cannot_be_set_to_allow` | passed | 2 |  |
| `test_p0_v4.GovernanceTests.test_mode_change_requires_confirm_and_persists` | passed | 12 |  |
| `test_p0_v4.GovernanceTests.test_policy_file_stays_inside_project_and_validates` | passed | 8 |  |
| `test_p0_v4.LLMClientTests.test_cache_reuses_non_sensitive_result` | passed | 14 |  |
| `test_p0_v4.LLMClientTests.test_invalid_output_is_never_accepted` | passed | 20 |  |
| `test_p0_v4.LLMClientTests.test_local_only_refuses_hosted_provider` | passed | 3 |  |
| `test_p0_v4.LLMClientTests.test_missing_key_is_a_clear_error` | passed | 2 |  |
| `test_p0_v4.LLMClientTests.test_rate_limit_is_retried` | passed | 5005 |  |
| `test_p0_v4.LLMClientTests.test_request_budget_is_enforced` | passed | 6 |  |
| `test_p0_v4.LLMClientTests.test_unavailable_provider_fails_loudly` | passed | 3 |  |
| `test_p0_v4.LLMClientTests.test_valid_output_is_returned_after_repair` | passed | 12 |  |
| `test_p0_v4.LLMSchemaTests.test_missing_required_field_is_rejected` | passed | 1 |  |
| `test_p0_v4.LLMSchemaTests.test_parse_json_handles_fences` | passed | 0 |  |
| `test_p0_v4.LLMSchemaTests.test_parse_json_rejects_non_json` | passed | 0 |  |
| `test_p0_v4.LLMSchemaTests.test_valid_understanding_passes` | passed | 0 |  |
| `test_p0_v4.LLMSchemaTests.test_wrong_enum_and_type_are_rejected` | passed | 0 |  |
| `test_p0_v4.OperationTests.test_cancel_running_operation_kills_local_process` | passed | 270 |  |
| `test_p0_v4.OperationTests.test_cleanup_refuses_active_and_removes_finished` | passed | 168 |  |
| `test_p0_v4.OperationTests.test_meshy_cancel_is_not_faked` | passed | 1 |  |
| `test_p0_v4.OperationTests.test_operation_record_is_persisted` | passed | 12 |  |
| `test_p0_v4.OperationTests.test_recover_marks_interrupted_without_claiming_success` | passed | 20 |  |
| `test_p0_v4.OperationTests.test_status_reports_honest_remote_cancel_limit` | passed | 3 |  |
| `test_p0_v4.OperationTests.test_tracked_command_completes` | passed | 131 |  |
| `test_p0_v4.OperationTests.test_tracked_command_timeout_is_reported` | passed | 1168 |  |
| `test_p0_v4.ReasoningTests.test_director_refuses_project_content_without_flag` | passed | 17 |  |
| `test_p0_v4.ReasoningTests.test_fallback_without_provider_is_labelled` | passed | 13 |  |
| `test_p0_v4.ReasoningTests.test_hybrid_specification_keeps_deterministic_structure` | passed | 24 |  |
| `test_p0_v4.ReasoningTests.test_llm_requires_explicit_confirm` | passed | 11 |  |
| `test_p0_v4.ReasoningTests.test_llm_understanding_preserves_original_and_limits_questions` | passed | 5 |  |
| `test_p0_v4.ReasoningTests.test_prompt_injection_is_flagged` | passed | 6 |  |
| `test_p0_v4.ReasoningTests.test_review_requires_confirm_and_returns_advice` | passed | 5 |  |
| `test_p0_v4.ReasoningTests.test_secret_redaction` | passed | 2 |  |
| `test_p0_v4.ServerToolTests.test_all_tools_have_handlers` | passed | 2 |  |
| `test_p0_v4.ServerToolTests.test_cancel_operation_requires_confirm_via_tool` | passed | 4 |  |
| `test_p0_v4.ServerToolTests.test_governance_tools_round_trip` | passed | 14 |  |
| `test_p0_v4.ServerToolTests.test_llm_status_never_returns_a_key` | passed | 3 |  |
| `test_p0_v4.ServerToolTests.test_new_control_tools_are_registered` | passed | 1 |  |
| `test_p0_v4.ServerToolTests.test_stdio_handshake_and_threaded_tool_call` | passed | 312 |  |
| `test_p0_v4.ServerToolTests.test_understanding_tool_falls_back_offline` | passed | 13 |  |
| `test_p0_v4.VerificationTests.test_command_must_be_argv_not_shell_string` | passed | 36 |  |
| `test_p0_v4.VerificationTests.test_failing_command_does_not_upgrade_status` | passed | 192 |  |
| `test_p0_v4.VerificationTests.test_inspect_reports_gaps_and_original_wording` | passed | 33 |  |
| `test_p0_v4.VerificationTests.test_no_command_means_no_execution` | passed | 36 |  |
| `test_p0_v4.VerificationTests.test_second_run_compares_with_previous` | passed | 354 |  |
| `test_p0_v4.VerificationTests.test_successful_command_upgrades_to_tested_with_evidence` | passed | 195 |  |
| `test_p0_v4.VerificationTests.test_verification_requires_execute_permission_confirm` | passed | 30 |  |
| `registry.unique_tool_names` | passed | 0 |  |
| `registry.every_tool_has_handler` | passed | 0 |  |
| `registry.nonempty_schemas` | passed | 0 |  |
| `registry.p0_v4_tools_present` | passed | 0 |  |
| `transport.stdio_handshake` | passed | 0 |  |

## Unverified dependencies

- Real Blender execution is not exercised by the offline suite.
- Unity/Unreal/Godot builds are not exercised without installed editors.
- Meshy, Sketchfab and LLM calls are mocked or skipped without credentials.
- A passed regression suite is not proof that a game build is playable.

## Notes

- External services are mocked only in isolated unit tests and are labelled as such.
- No paid API is required by this suite.
- Passing tests do not prove a game build runs or is fun.
