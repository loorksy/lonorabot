import { useEffect, useState } from "react";
import { api, isRequestCancelled } from "../../lib/api";
import { useClient } from "../../providers/ClientProvider";

/** What GET /api/owner/profile returns (the parts the settings pages read). */
export type OwnerProfile = {
  content: string;
  version: number;
  name: string | null;
  address: string | null;
  reply_language: "ar" | "en" | null;
  reach_me: import("@lonora/contracts").IncomingCallPolicy;
  devices: { id: string; name: string }[];
  limit: number;
};

/** The owner profile, read again when the server says something changed. */
export function useOwnerProfile() {
  const { revision } = useClient();
  const [profile, setProfile] = useState<OwnerProfile | null>(null);
  useEffect(() => {
    void revision;
    let live = true;
    api.get<OwnerProfile>("/owner/profile").then(
      (value) => {
        if (live) setProfile(value);
      },
      (error) => {
        if (!isRequestCancelled(error)) console.warn("owner_profile_unavailable", error);
      },
    );
    return () => {
      live = false;
    };
  }, [revision]);
  return [profile, setProfile] as const;
}
