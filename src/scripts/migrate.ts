import { runMigrations } from '../migrations';

async function main() {
  const { applied } = await runMigrations();
  // eslint-disable-next-line no-console
  console.log(`Migrations applied: ${applied.length ? applied.join(', ') : '(none)'}`);
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err);
    process.exit(1);
  });
