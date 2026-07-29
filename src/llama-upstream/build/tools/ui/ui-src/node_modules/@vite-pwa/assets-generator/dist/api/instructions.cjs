'use strict';

async function instructions(imageAssets) {
  return await import('../chunks/instructions-resolver.cjs').then(({ resolveInstructions }) => resolveInstructions(imageAssets));
}

exports.instructions = instructions;
