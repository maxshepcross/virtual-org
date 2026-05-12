import { bulkAddHorses, countHorses } from "../lib/queries";
import { STARTER_HORSES } from "../lib/starter-horses";

async function main() {
  const fs = await import("node:fs/promises");
  const path = await import("node:path");
  const customPath = path.resolve(process.cwd(), "data/horses.txt");

  let names: string[];
  try {
    const text = await fs.readFile(customPath, "utf8");
    names = text
      .split(/\r?\n/)
      .map((line) => line.replace(/^\s*#.*$/, "").trim())
      .filter((line) => line.length > 0);
    console.log(`Loaded ${names.length} horse names from data/horses.txt`);
  } catch {
    names = [...STARTER_HORSES];
    console.log(
      `data/horses.txt not found; seeding ${names.length} starter horses. ` +
        `Drop a one-name-per-line file at data/horses.txt and re-run to import the real pool.`,
    );
  }

  const before = countHorses();
  const { added, skipped } = bulkAddHorses(names);
  const after = countHorses();
  console.log(
    `Horses: ${before} → ${after}  (added: ${added}, skipped duplicates: ${skipped})`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
