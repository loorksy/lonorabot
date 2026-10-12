import { Trans } from "@lingui/react/macro";
import type { Routine } from "@lonora/contracts";

export type Schedule = {
  mode: "interval" | "cron";
  minutes: number;
  cron: string;
  timezone: string;
};
export function RoutineSchedule({
  value,
  onChange,
}: {
  value: Schedule;
  onChange: (value: Schedule) => void;
}) {
  return (
    <div className="form-grid">
      <label>
        <Trans>Schedule</Trans>
        <select
          value={value.mode}
          onChange={(event) => onChange({ ...value, mode: event.target.value as Schedule["mode"] })}
        >
          <option value="interval">
            <Trans>Interval</Trans>
          </option>
          <option value="cron">
            <Trans>Cron expression</Trans>
          </option>
        </select>
      </label>
      {value.mode === "interval" ? (
        <label>
          <Trans>Every · minutes</Trans>
          <input
            type="number"
            required
            min={1}
            max={525600}
            value={value.minutes}
            onChange={(event) => onChange({ ...value, minutes: Number(event.target.value) })}
          />
        </label>
      ) : (
        <label>
          <Trans>Cron expression</Trans>
          <input
            required
            dir="ltr"
            value={value.cron}
            onChange={(event) => onChange({ ...value, cron: event.target.value })}
          />
        </label>
      )}
      <label>
        <Trans>Timezone</Trans>
        <input
          required
          dir="ltr"
          value={value.timezone}
          onChange={(event) => onChange({ ...value, timezone: event.target.value })}
        />
      </label>
    </div>
  );
}
export function RoutineScheduleSummary({ routine }: { routine: Routine }) {
  return (
    <bdi>
      {routine.cron ?? `${routine.interval_seconds}s`} · {routine.timezone}
    </bdi>
  );
}
