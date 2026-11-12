# lonora-controls.sh — the owner-control fingerprint of `lonora update` (docs/operations.md).
#
# Sourced by infra/compose/lonora, which provides psql_value (one value from the bundled
# database; non-zero when the query fails). `lonora update` sources the TARGET release's
# copy of this file, taken from the image it installs, before it reads the baseline after
# the migrations, and a rollback of that update compares with the same copy. So a release
# that removes a control removes it from both sides of the comparison, and the definition
# always describes the schema the target release migrated to.
#
# Owner controls, authority and money records. If any of them changed while a new version
# ran, restoring the pre-update backup could undo an owner's pause, restriction or
# revocation, or erase the record of an order already at the broker: the rollback holds.
# Every part is read only when its table exists, so a table a release dropped never makes
# the records unreadable.
CONTROL_TABLES=(ln_trading_restrictions ln_account_authorities ln_supervision_grants ln_supervision_holds ln_owner_actions ln_trade_approvals ln_trading_journal)

# A digest of the rows a query selects, each row hashed on its own so the aggregate stays
# small whatever the table size; "absent" when the table does not exist; empty (and
# non-zero) when the database cannot be read.
control_part() { # $1 table, $2 row expression over t, $3 WHERE clause (optional)
    local exists
    exists="$(psql_value "SELECT CASE WHEN to_regclass('$1') IS NULL THEN 'absent' ELSE 'present' END")" || return 1
    case "$exists" in
        absent) printf 'absent\n'; return 0 ;;
        present) ;;
        *) return 1 ;;
    esac
    psql_value "SELECT md5(coalesce(string_agg(r.h, '' ORDER BY r.h), '')) FROM (SELECT md5($2) AS h FROM $1 t ${3:-}) r"
}

# One sha256 of every owner-control, authority and money record (whole rows), the owner's
# pauses of agents and tasks, the broker connections'
# enabled flags and the owner's own messages. Empty when the database cannot be read.
control_fingerprint() {
    local table part all=""
    control_add() { # $1 name, then control_part's arguments
        local name="$1"; shift
        part="$(control_part "$@")" || return 1
        [[ -n "$part" ]] || return 1
        all+="$name=$part;"
    }
    for table in "${CONTROL_TABLES[@]}"; do
        control_add "$table" "$table" 't::text' || return 0
    done
    control_add agent_pauses ln_agents "t.id || ':' || t.paused::text" 'WHERE t.paused' || return 0
    control_add connections ln_broker_sessions "t.id || ':' || coalesce(t.payload->>'enabled', '')" || return 0
    control_add task_exits ln_tickets \
        "t.id || ':' || coalesce(t.state->>'control_requested', '') || ':' || CASE WHEN t.state->>'status' IN ('paused', 'cancelled') THEN t.state->>'status' ELSE '' END" \
        "WHERE t.state->>'control_requested' IS NOT NULL OR t.state->>'status' IN ('paused', 'cancelled')" || return 0
    control_add owner_messages ln_messages 't::text' "WHERE role = 'user'" || return 0
    printf '%s\n' "$all" | sha256sum | cut -d' ' -f1
}
