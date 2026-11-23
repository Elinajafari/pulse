// Put the demo on the explorer: a bond that is kept, a bond that is breached by
// a dead address, a bond that is failed by a page that says it is down, and the
// refusals.
//
//   pnpm demo:contract        (after pnpm deploy:contract)
//
// The three health addresses are files in this repository, read through
// raw.githubusercontent.com:
//
//   healthy.txt    answers 200 and says the service is running
//   gone.txt       was never committed, so it answers 404
//   degraded.txt   answers 200 and says the service is under maintenance
//
// StudioNet charges a fee on every write, so a wallet's balance cannot show what
// it was paid. What each wallet received is read from the chain's own index: the
// transfers the contract sent it.

import { readFileSync, writeFileSync } from "node:fs";
import { RECORD_FILE, accountFrom, clientFor, fundAccount, loadEnv, network, readRetry, recorder, sleep, sourceSha256 } from "./lib.mjs";

loadEnv();
const net = network();
const record = JSON.parse(readFileSync(RECORD_FILE, "utf8"));
if (record.source_sha256 !== sourceSha256()) throw new Error("pulse.py changed since it was deployed; run pnpm deploy:contract first");
const address = record.contract;
const GEN = 10n ** 18n;
const RAW = "https://raw.githubusercontent.com/Elinajafari/pulse/main/demo";
const HEALTHY = `${RAW}/healthy.txt`;
const GONE = `${RAW}/gone.txt`;
const DEGRADED = `${RAW}/degraded.txt`;
const STAKE = GEN / 20n; // 0.05 GEN a bond
const GAP = 60n;

const ROLES = ["provider", "beneficiary", "stranger"];
const who = Object.fromEntries(ROLES.map((k) => [k, accountFrom(`${k.toUpperCase()}_PRIVATE_KEY`, net)]));
const as = Object.fromEntries(ROLES.map((k) => [k, clientFor(net, who[k])]));
const ro = clientFor(net, null);
const read = (fn, args = []) => readRetry(() => ro.readContract({ address, functionName: fn, args }));
const plain = (v) => JSON.parse(JSON.stringify(v, (_, x) => (typeof x === "bigint" ? Number(x) : x instanceof Map ? Object.fromEntries(x) : x)));
const rec = recorder();

async function waitUntilMs(target, label) {
  const left = target - Date.now();
  if (left > 0) { console.log(`  waiting ${Math.ceil(left / 1000)}s for ${label}`); await sleep(left); }
}
const waitUntil = (stamp, label) => waitUntilMs(Date.parse(stamp) + 15_000, label);

/** The finalized transfers the contract sent `to`, from the chain's own index. */
async function incoming(to) {
  const rows = await readRetry(() => ro.request({ method: "sim_getTransactionsForAddress", params: [to] }));
  return rows.filter((r) => String(r.from_address ?? "").toLowerCase() === address.toLowerCase()
    && String(r.to_address ?? "").toLowerCase() === to.toLowerCase() && String(r.status) === "FINALIZED")
    .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
}

console.log(`\ncontract ${address}`);
if (Number(await read("count")) !== 0) throw new Error("the demo expects a fresh contract");
if (net.name === "studionet") for (const k of ROLES) await fundAccount(net, ro, who[k].address, 2n * GEN);

const w = (k, fn, args, opts) => rec.write(as[k], who[k], address, fn, args, opts);
const benef = who.beneficiary.address;

await w("provider", "open", [benef, "Orders API, healthy", HEALTHY, GAP, 2n, 420n], { step: "bond 0 opened: a healthy address, 2 failed probes in a row are a breach", value: STAKE });
await w("provider", "open", [benef, "Orders API, address gone", GONE, GAP, 2n, 420n], { step: "bond 1 opened: an address that answers 404", value: STAKE });
await w("provider", "open", [benef, "Orders API, in maintenance", DEGRADED, GAP, 2n, 300n], { step: "bond 2 opened: an address that answers 200 and says it is down", value: STAKE });

await w("stranger", "probe", [0n], { step: "bond 0, probe 1: the page answers 200 and reads healthy: up" });
await w("stranger", "probe", [0n], { step: "bond 0: a probe sooner than the gap: refused", expect: "refused" });
await w("stranger", "probe", [1n], { step: "bond 1, probe 1: the address answers 404: down, strike 1" });
await w("stranger", "probe", [2n], { step: "bond 2, probe 1: 200 but the page says maintenance: down, strike 1" });

const last = Math.max(...(await Promise.all([0n, 1n, 2n].map(async (i) => Date.parse((await read("probes_of", [i])).probes.at(-1).at)))));
await waitUntilMs(last + Number(GAP) * 1000 + 15_000, "the gap since the last probe");
await w("stranger", "probe", [0n], { step: "bond 0, probe 2: healthy again: up" });
await w("stranger", "probe", [1n], { step: "bond 1, probe 2: 404 again: strike 2, the bond is breached and the stake is paid out" });
await w("stranger", "probe", [1n], { step: "a probe on a breached bond: refused", expect: "refused" });
await w("stranger", "settle", [0n], { step: "a settlement while bond 0's term is still running: refused", expect: "refused" });

await waitUntil((await read("bond", [2n])).deadline, "bond 2's term to end");
await w("stranger", "settle", [2n], { step: "bond 2 settled: only one failure, never a breach: the stake returns to the provider" });
await waitUntil((await read("bond", [0n])).deadline, "bond 0's term to end");
await w("stranger", "settle", [0n], { step: "bond 0 settled: never breached: the stake returns to the provider" });
await w("stranger", "settle", [1n], { step: "a settlement of a breached bond: refused", expect: "refused" });

const n = Number(await read("count"));
const bonds = [], probes = [];
for (let k = 0; k < n; k++) { bonds.push(plain(await read("bond", [BigInt(k)]))); probes.push(plain(await read("probes_of", [BigInt(k)]))); }
const owed = { provider: 0n, beneficiary: 0n };
for (const b of bonds) {
  if (b.status === "breached") owed.beneficiary += BigInt(b.stake);
  else if (b.status === "kept") owed.provider += BigInt(b.stake);
}

// The payouts land after the receipt: read the index until they have arrived.
const payouts = {}, received = {};
for (const k of ["provider", "beneficiary"]) {
  let rows = [];
  for (let i = 0; i < 40; i++) {
    rows = await incoming(who[k].address);
    if (rows.reduce((s, r) => s + BigInt(r.value), 0n) >= owed[k]) break;
    await sleep(8_000);
  }
  payouts[k] = rows.map((r) => ({ tx: r.hash, value: String(BigInt(r.value)), created_at: String(r.created_at) }));
  received[k] = String(rows.reduce((s, r) => s + BigInt(r.value), 0n));
}

record.steps.push(...rec.steps);
record.demo = {
  addresses: { healthy: HEALTHY, gone: GONE, degraded: DEGRADED },
  stake_wei: String(STAKE),
  bonds, probes,
  owed: Object.fromEntries(Object.entries(owed).map(([k, v]) => [k, String(v)])),
  received, payouts,
  held_after: String(await read("held_total")),
  accounts: Object.fromEntries(ROLES.map((k) => [k, who[k].address])),
};
writeFileSync(RECORD_FILE, JSON.stringify(record, null, 2) + "\n");
console.log(`\nprovider received ${received.provider} (owed ${owed.provider}); beneficiary received ${received.beneficiary} (owed ${owed.beneficiary}); record written to ${RECORD_FILE}\n`);
