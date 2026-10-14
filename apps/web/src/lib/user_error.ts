import { t } from "@lingui/core/macro";
import { errorCode } from "@lonora/core";
export function userError(error: unknown) {
  const code = errorCode(error);
  switch (code) {
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
    case "broker_account_not_found":
      return t`Broker account not found.`;
    case "broker_credentials_rejected":
      return t`Broker authentication was rejected.`;
    case "broker_candles_timeout":
      return t`Historical broker candles timed out. Retry the chart refresh.`;
    case "broker_candles_request_rejected":
      return t`The broker rejected this timeframe or candle request.`;
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
