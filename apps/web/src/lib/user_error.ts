import { i18n } from "@lingui/core";
import { t } from "@lingui/core/macro";
import {
  agentPermissionError,
  errorCode,
  financialBoundaryError,
  ownerActionError,
  ownerProfileError,
  supervisionError,
} from "@lonora/core";
import { isRequestCancelled } from "./api";
export function userError(error: unknown) {
  if (isRequestCancelled(error)) return "";
  const code = errorCode(error);
  const permissionMessage = agentPermissionError(code, i18n.locale);
  if (permissionMessage) return permissionMessage;
  // Boundary blocks: why nothing was sent, in text shared with Mobile (@lonora/core).
  const boundaryMessage = financialBoundaryError(code, i18n.locale);
  if (boundaryMessage) return boundaryMessage;
  const cardMessage = ownerActionError(code, i18n.locale);
  if (cardMessage) return cardMessage;
  const profileMessage = ownerProfileError(code, i18n.locale);
  if (profileMessage) return profileMessage;
  const supervisionMessage = supervisionError(code, i18n.locale);
  if (supervisionMessage) return supervisionMessage;
  switch (code) {
    case "agent_scope_change_forbidden":
      return t`This agent’s market scope cannot be changed.`;
    case "agent_scope_change_incomplete":
      return t`Choose a complete market scope and reload the saved settings before continuing.`;
    case "collaboration_guest_limit":
      return t`At most two other agents can join one message.`;
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
    case "shadow_execution_forbidden":
      return t`Execution mode changed. Review the saved plan before continuing.`;
    case "device_challenge_not_found":
      return t`This passkey request is not available in this session. Start it again.`;
    case "device_secure_origin_required":
      return t`Use the configured secure website for device authentication.`;
    case "device_registration_required":
      return t`Register a passkey before activating this request.`;
    case "device_authorization_required":
      return t`This needs a new grant you sign with your passkey.`;
    case "device_authorization_cancelled":
      return t`Device authentication was cancelled. No authority was granted.`;
    case "device_not_supported":
      return t`Secure device authentication is unavailable on this device.`;
    case "device_proof_invalid":
      return t`Device verification failed. No authority was granted.`;
    case "device_challenge_expired_or_used":
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
    case "model_access_denied":
      return t`This API key cannot use the selected model. Choose another model or check the provider account’s model access.`;
    case "model_billing_exhausted":
      return t`Your model provider account is out of credits or over its spending limit. Add credit or choose another provider.`;
    case "model_content_blocked":
      return t`The model provider’s safety system withheld this answer.`;
    case "model_output_truncated":
      return t`The model’s answer was cut off at its output limit. Try again or ask for a shorter answer.`;
    case "model_endpoint_unavailable":
      return t`The selected model is not available from this provider. Choose another model in Settings.`;
    case "model_provider_unavailable":
      return t`The model provider is unavailable right now. Try again shortly.`;
    case "model_request_rejected":
      return t`The model provider rejected this request.`;
    case "model_response_invalid":
      return t`The model provider returned an unreadable response. Try again.`;
    case "broker_trading_not_allowed":
      return t`This broker account does not permit trading. Check its trading permissions.`;
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
    case "operation_in_progress":
      return t`This operation is still in progress. Wait for its broker result before resolving it.`;
    case "operation_already_settled":
      return t`This operation already has a settled outcome. Reload the journal.`;
    case "broker_account_not_found":
      return t`Broker account not found.`;
    case "connection_test_timeout":
      return t`The test did not get an answer in time. Nothing was saved.`;
    case "broker_secret_required":
      return t`Enter the access token.`;
    case "broker_account_already_connected":
      return t`This broker account is already connected. Use the existing connection.`;
    case "broker_identity_unavailable":
      return t`The broker account could not be verified. Check its connection details and try again.`;
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
      return t`This step was interrupted and picked up again. Nothing was repeated.`;
    case "task_reconciliation_required":
      return t`This task is waiting for an uncertain external operation to be reconciled.`;
    case "task_cannot_resume":
    case "task_retry_limit":
      return t`This task cannot resume in its current state. Review its plan or retry limit.`;
    case "context_limit_exceeded":
    case "history_message_too_large":
    case "history_summary_too_large":
      return t`This message is too large to process, even after older history was summarized. Shorten it or send fewer attachments; the conversation is kept.`;
    case "history_summary_empty":
      return t`The model could not summarize this conversation. Retry or choose another global model.`;
    case "invalid_tool_exchange":
      return t`Part of this conversation's history could not be read, so this reply stopped. Send your message again; the conversation is kept.`;
    case "tool_round_limit":
      return t`I paused at this run's step budget. Send a message and I continue from here.`;
    default:
      return t`The request could not be completed. Try again.`;
  }
}
