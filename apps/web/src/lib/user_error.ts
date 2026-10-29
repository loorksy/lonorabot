import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import { agentPermissionError, errorCode } from "@lonora/core";
import { isRequestCancelled } from "./api";
export function userError(error: unknown) {
  if (isRequestCancelled(error)) return "";
  const code = errorCode(error);
  const permissionMessage = agentPermissionError(code, i18n.locale);
  if (permissionMessage) return permissionMessage;
  switch (code) {
    case "input_answer_invalid":
      return t`Choose an available answer.`;
    case "input_answer_expired":
      return t`This question is no longer waiting for an answer.`;
    case "input_answer_conflict":
      return t`A different answer was already recorded.`;
    case "skill_revocation_limit":
      return t`This agent has reached its blocked-version limit. Existing blocks have been preserved.`;
    case "skill_package_lifecycle_required":
      return t`This procedure requires a validated version before it can be enabled or changed.`;
    case "skill_not_found":
      return t`This skill is no longer in the current catalog. Reload the list.`;
    case "skill_controls_invalid":
    case "skill_control_scope_mismatch":
      return t`Skill version controls could not be verified. Reload before making changes.`;
    case "skill_manifest_invalid":
    case "skill_manifest_identity_invalid":
      return t`Review the skill identity, version and manifest before saving.`;
    case "skill_reference_missing":
    case "skill_dependency_cycle":
    case "skill_duplicate_id":
      return t`Review skill dependencies and unique identities before saving.`;
    case "skill_continuation_unavailable":
      return t`An active skill is no longer available. Review its settings before resuming this task.`;
    case "personal_agent_cannot_delete":
      return t`Your Personal Agent cannot be deleted.`;
    case "execution_mode_changed":
    case "goal_execution_mode_invalid":
    case "shadow_execution_forbidden":
      return t`Execution mode changed. Review the saved plan before continuing.`;
    case "shadow_monetary_pnl_unavailable":
      return t`Virtual monetary profit is unavailable without verified contract and currency valuation.`;
    case "shadow_decision_required":
      return t`Record a fresh market decision before virtual entry.`;
    case "super_bot_advisory_only":
      return t`This plan is advisory and cannot execute trades.`;
    case "super_bot_scope_changed":
    case "device_challenge_not_found":
    case "super_bot_manual_permission_required":
      return t`Review a new Super Bot request and authorize it with your device.`;
    case "device_secure_origin_required":
      return t`Use the configured secure website for device authentication.`;
    case "device_registration_required":
      return t`Register a passkey before activating this request.`;
    case "device_authorization_required":
    case "super_bot_authority_expansion":
      return t`Review a new Super Bot request and authorize it with your device.`;
    case "device_authorization_cancelled":
      return t`Device authentication was cancelled. No authority was granted.`;
    case "device_not_supported":
      return t`Secure device authentication is unavailable on this device.`;
    case "device_proof_invalid":
      return t`Device verification failed. No authority was granted.`;
    case "device_challenge_expired_or_used":
    case "super_bot_request_expired_or_used":
    case "super_bot_request_expired_or_changed":
    case "super_bot_plan_changed":
      return t`This authorization request expired or changed. Review a new request.`;
    case "unauthorized":
      return t`Sign-in failed. Check your email and password.`;
    case "invalid_bootstrap_token":
      return t`The setup code is incorrect.`;
    case "model_not_configured":
      return t`Connect a provider and choose a global model in Settings.`;
    case "model_rate_limited":
      return t`The model provider rate limit was reached. Try again shortly.`;
    case "model_credentials_rejected":
      return t`The provider rejected this API key.`;
    case "trading_disabled":
      return t`Trading is off.`;
    case "emergency_stop":
      return t`Emergency stop is active.`;
    case "broker_trading_not_allowed":
      return t`This broker account does not permit trading. Check its trading permissions.`;
    case "goal_autonomy_required":
    case "goal_owner_control_required":
      return t`Enable autonomous trading for this goal in its owner controls first.`;
    case "goal_volume_limit_required":
    case "goal_volume_limit":
    case "goal_action_limit":
      return t`Review this goal's volume and action limits before continuing.`;
    case "goal_reconciliation_required":
    case "goal_target_ambiguous":
    case "goal_owner_retry_required":
      return t`This goal is waiting for broker verification. Its financial operation will not be repeated automatically.`;
    case "goal_not_active":
    case "goal_terminal":
      return t`This goal is paused, cancelled or completed. Reload its current state.`;
    case "goal_condition_unmet":
    case "goal_condition_stale":
      return t`The current market no longer confirms this goal's condition. No trade was sent.`;
    case "goal_target_pending":
      return t`Waiting for the broker to report the entry position. The accepted order will not be submitted again.`;
    case "version_conflict":
      return t`This item changed. Reload it before saving.`;
    case "voice_transport_not_configured":
      return t`Configure an OpenAI credential with GPT-Live access to start a voice call.`;
    case "voice_permission_denied":
      return t`Allow microphone access to start a voice conversation.`;
    case "voice_browser_unsupported":
      return t`Voice requires a browser with WebRTC and microphone support on HTTPS.`;
    case "voice_model_unavailable":
      return t`GPT-Live is not available for this OpenAI project. Check its API access.`;
    case "voice_backend_unavailable":
      return t`The resident voice worker is unavailable. Check server readiness and retry.`;
    case "voice_response_invalid":
    case "voice_connection_failed":
      return t`The voice connection failed. Retry the call.`;
    case "voice_model_unsupported":
      return t`Choose GPT-Live 1 or GPT-Live 1 mini as the global voice model.`;
    case "voice_provider_unsupported":
      return t`Choose supported global speech models in Settings.`;
    case "chart_initializing":
      return t`The resident worker is preparing this chart.`;
    case "chart_data_unavailable":
    case "broker_candles_unavailable":
      return t`Broker candles are unavailable for this symbol and timeframe.`;
    case "symbol_not_found":
      return t`This exact symbol is not available from your broker.`;
    case "broker_reconciliation_pending":
    case "broker_reconciliation_required":
      return t`Broker verification pending. Market data may remain available; trading is blocked until verification finishes.`;
    case "broker_account_not_found":
      return t`Broker account not found.`;
    case "broker_account_mismatch":
      return t`Broker data does not match the selected account. Nothing was sent.`;
    case "broker_account_undeployed":
      return t`The broker connection is stopped at the connection provider. Start it there, then retry.`;
    case "broker_account_not_ready":
      return t`The broker account is not ready at the connection provider. Check its status, then retry.`;
    case "broker_credentials_rejected":
      return t`Broker authentication was rejected.`;
    case "broker_candles_timeout":
      return t`Historical broker candles timed out. Retry the chart refresh.`;
    case "broker_candles_request_rejected":
      return t`The broker rejected this timeframe or candle request.`;
    case "broker_market_data_billing_required":
      return t`Historical market data is blocked by the data provider's billing. Fund the provider account, then retry. Live prices may remain available.`;
    case "broker_rate_limited":
      return t`The broker market-data service is rate limited.`;
    case "broker_candles_not_found":
      return t`No candle history was found for this symbol and timeframe.`;
    case "broker_candles_mismatch":
    case "broker_candles_invalid":
      return t`Broker candles contain invalid or mismatched data.`;
    case "unsupported_timeframe":
      return t`That chart timeframe is not supported by this broker.`;
    case "broker_quote_unavailable":
      return t`The broker quote is unavailable for this exact symbol.`;
    case "broker_instrument_unavailable":
      return t`The broker specifications are unavailable for this exact symbol.`;
    case "broker_disabled":
      return t`This broker connection is disabled.`;
    case "broker_connection_changed":
    case "broker_configuration_changed":
      return t`The broker connection changed. Reload it before continuing.`;
    case "mutation_evidence_required":
      return t`The broker mutation is uncertain. Execution remains blocked until its result can be verified.`;
    case "broker_history_unavailable":
      return t`Broker deal history is unavailable for this time range.`;
    case "broker_connection_unavailable":
      return t`The broker connection is unavailable.`;
    case "simulation_snapshot_required":
      return t`Import a market snapshot before using the demo account.`;
    case "invalid_request":
      return t`Check the required fields and try again.`;
    case "rate_limited":
      return t`Too many attempts. Wait a minute and retry.`;
    case "stale_lease":
      return t`This run was recovered by another worker.`;
    case "task_reconciliation_required":
      return t`This task is waiting for an uncertain external operation to be reconciled.`;
    case "task_cannot_resume":
    case "task_retry_limit":
      return t`This task cannot resume in its current state. Review its plan or retry limit.`;
    case "context_limit_exceeded":
    case "history_message_too_large":
    case "history_summary_too_large":
      return t`This conversation is too large to process. Shorten instructions, use fewer attachments, or start a new conversation.`;
    case "history_summary_empty":
      return t`The model could not summarize this conversation. Retry or choose another global model.`;
    case "invalid_tool_exchange":
      return t`This conversation could not be resumed. Start a new conversation.`;
    case "tool_round_limit":
      return t`The agent reached the step limit for this run. Send another message to continue.`;
    default:
      return t`The request could not be completed. Try again.`;
  }
}
