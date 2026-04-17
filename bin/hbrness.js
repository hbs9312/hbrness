#!/usr/bin/env node
const { main } = require('../scripts/install/cli.js');

main(process.argv.slice(2)).catch((err) => {
  console.error(`\x1b[31merror:\x1b[0m ${err.message}`);
  if (process.env.HBRNESS_DEBUG) {
    console.error(err.stack);
  }
  process.exit(1);
});
