import { Trans } from "@lingui/react/macro";
import type { SkillManifest } from "@lonora/contracts";

export function SkillMetadata({ manifest }: { manifest: SkillManifest }) {
  return (
    <dl className="skill-metadata">
      <dt>
        <Trans>Dependencies</Trans>
      </dt>
      <dd>
        <bdi dir="ltr">{manifest.dependencies.join(", ") || "—"}</bdi>
      </dd>
      <dt>
        <Trans>Required tools</Trans>
      </dt>
      <dd>
        <bdi dir="ltr">{manifest.required_tools.join(", ") || "—"}</bdi>
      </dd>
      <dt>
        <Trans>Required capabilities</Trans>
      </dt>
      <dd>
        <bdi dir="ltr">{manifest.required_capabilities.join(", ") || "—"}</bdi>
      </dd>
    </dl>
  );
}
