"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const migrations_1 = require("../migrations");
async function main() {
    const { applied } = await (0, migrations_1.runMigrations)();
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
