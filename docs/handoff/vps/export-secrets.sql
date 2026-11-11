-- Run inside the OLD lonora-db (read-only). Ciphertext stays encrypted; no value is decrypted here.
select json_build_object(
  'secrets', coalesce((select json_agg(json_build_object('id', id, 'scope', scope, 'name', name, 'ciphertext', ciphertext) order by scope, name) from ln_secrets), '[]'::json),
  'brokers', coalesce((select json_agg(payload) from ln_broker_sessions), '[]'::json)
);
