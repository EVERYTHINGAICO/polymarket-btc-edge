// Sandbox (READ-ONLY): leer el Conditional Tokens Framework (CTF) en Polygon
// para ver como resolvio on-chain un mercado BTC 15-min real, y quien es el oraculo.
// NO firma, NO opera, NO toca fondos. Solo eth_call / getLogs de lectura.
const { ethers } = require("ethers");

const RPC = "https://polygon-bor-rpc.publicnode.com";
const CTF = "0x4d97dcd97ec945f40cf65f87097ace5ea0476045"; // Conditional Tokens (Gnosis)

const ABI = [
  "function getOutcomeSlotCount(bytes32 conditionId) view returns (uint256)",
  "function payoutDenominator(bytes32 conditionId) view returns (uint256)",
  "function payoutNumerators(bytes32 conditionId, uint256 index) view returns (uint256)",
  "event ConditionPreparation(bytes32 indexed conditionId, address indexed oracle, bytes32 indexed questionId, uint256 outcomeSlotCount)",
  "event ConditionResolution(bytes32 indexed conditionId, address indexed oracle, bytes32 indexed questionId, uint256 outcomeSlotCount, uint256[] payoutNumerators)"
];

const CONDS = [
  ["0x7823ca7095575b322bc6c609b70e271a2ba9d95efa7daa5d82deaa7510f5218b", "Dec26 7:30-7:45 -> Up"],
  ["0x9225ae2f853ce91c9e507953470437497b4260313ccb7c902e647ea261e42abe", "Feb21 9:45-10:00 -> Down"],
  ["0x4d1ad8866da96b7c3eb35730ba0689bcac1995061e506cbc60d5757c1f54e395", "Feb21 9:30-9:45 -> Up"],
];

async function main() {
  const p = new ethers.JsonRpcProvider(RPC);
  const ctf = new ethers.Contract(CTF, ABI, p);
  console.log("CTF:", CTF, "| RPC block:", await p.getBlockNumber(), "\n");

  for (const [cid, label] of CONDS) {
    console.log(`--- ${label}\n    conditionId ${cid.slice(0,18)}...`);
    const slots = await ctf.getOutcomeSlotCount(cid);
    const den = await ctf.payoutDenominator(cid);
    console.log(`    outcomeSlots=${slots}  payoutDenominator=${den} ${den==0n?"(NO resuelto on-chain)":""}`);
    if (slots > 0n && den > 0n) {
      const nums = [];
      for (let i = 0n; i < slots; i++) nums.push((await ctf.payoutNumerators(cid, i)).toString());
      console.log(`    payoutNumerators=[${nums.join(", ")}]  -> ganador = indice ${nums.indexOf("1")} (1=gana, 0=pierde)`);
    }
    // quien es el oraculo? ConditionPreparation tiene conditionId+oracle+questionId indexados
    try {
      const flt = ctf.filters.ConditionPreparation(cid);
      const logs = await ctf.queryFilter(flt, 0, "latest");
      if (logs.length) {
        const e = logs[0].args;
        console.log(`    ORACULO (quien reporta) = ${e.oracle}`);
        console.log(`    questionId = ${e.questionId.slice(0,18)}...`);
      } else console.log("    (sin evento ConditionPreparation en rango)");
    } catch (err) {
      console.log(`    [getLogs rechazado por el RPC: ${String(err.shortMessage||err.message).slice(0,80)}]`);
    }
    console.log();
  }
}
main().catch(e => { console.error("ERR:", e.message); process.exit(1); });
