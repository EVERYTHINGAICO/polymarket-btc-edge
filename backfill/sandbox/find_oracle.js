// READ-ONLY: identificar QUIEN resuelve los mercados BTC 15-min (el oraculo/adapter).
// Binary-search del bloque por timestamp + getLogs acotado de ConditionResolution.
const { ethers } = require("ethers");
const RPC = "https://polygon-bor-rpc.publicnode.com";
const CTF = "0x4d97dcd97ec945f40cf65f87097ace5ea0476045";
const ABI = [
  "event ConditionPreparation(bytes32 indexed conditionId, address indexed oracle, bytes32 indexed questionId, uint256 outcomeSlotCount)",
  "event ConditionResolution(bytes32 indexed conditionId, address indexed oracle, bytes32 indexed questionId, uint256 outcomeSlotCount, uint256[] payoutNumerators)"
];
const CONDS = [
  ["0x7823ca7095575b322bc6c609b70e271a2ba9d95efa7daa5d82deaa7510f5218b", 1766796300, "Dec26->Up"],
  ["0x4d1ad8866da96b7c3eb35730ba0689bcac1995061e506cbc60d5757c1f54e395", 1771685100, "Feb21 9:30->Up"],
  ["0x9225ae2f853ce91c9e507953470437497b4260313ccb7c902e647ea261e42abe", 1771686000, "Feb21 9:45->Down"],
];

async function blockAtTime(p, target) {
  let lo = 1, hi = await p.getBlockNumber();
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    const b = await p.getBlock(mid);
    if (b.timestamp < target) lo = mid + 1; else hi = mid;
  }
  return lo;
}

async function main() {
  const p = new ethers.JsonRpcProvider(RPC);
  const ctf = new ethers.Contract(CTF, ABI, p);
  for (const [cid, end_ts, label] of CONDS) {
    console.log(`--- ${label}  (end_ts ${end_ts})`);
    const blk = await blockAtTime(p, end_ts);
    console.log(`    bloque ~end_ts = ${blk}`);
    let found = false;
    for (const [a, b, tag] of [[blk-50, blk+2500, "resolucion"]]) {
      try {
        const logs = await ctf.queryFilter(ctf.filters.ConditionResolution(cid), a, b);
        if (logs.length) {
          const e = logs[0].args;
          console.log(`    [${tag}] ORACULO=${e.oracle}  questionId=${e.questionId.slice(0,18)}...  block=${logs[0].blockNumber}`);
          found = true;
        }
      } catch (err) { console.log(`    [${tag} getLogs err: ${String(err.shortMessage||err.message).slice(0,60)}]`); }
    }
    if (!found) console.log("    (no encontrado en ventana; ampliar)");
    console.log();
  }
}
main().catch(e => { console.error("ERR:", e.message); process.exit(1); });
