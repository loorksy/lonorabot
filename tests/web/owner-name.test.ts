import assert from "node:assert/strict";
import test from "node:test";
import { ownerDisplayName, ownerInitial } from "../../apps/web/src/shell/data";
import type { OwnerProfile } from "../../apps/web/src/shell/settings/owner";

const owner = { id: "o1", email: "ahmed@example.com" };
const profile = (name: string | null, address: string | null) =>
  ({ name, address }) as OwnerProfile;

test("the owner is called by the form of address, else the name, else the e-mail's local part", () => {
  assert.equal(ownerDisplayName(profile("Ahmed", "أبو سامي"), owner), "أبو سامي");
  assert.equal(ownerDisplayName(profile("Ahmed", ""), owner), "Ahmed");
  assert.equal(ownerDisplayName(profile(null, null), owner), "ahmed");
  assert.equal(ownerDisplayName(null, owner), "ahmed");
});

test("the avatar letter is the first character of that name, uppercased", () => {
  assert.equal(ownerInitial("ahmed"), "A");
  assert.equal(ownerInitial("أحمد"), "أ");
  assert.equal(ownerInitial("𝒜lex"), "𝒜");
  assert.equal(ownerInitial(""), "");
});
