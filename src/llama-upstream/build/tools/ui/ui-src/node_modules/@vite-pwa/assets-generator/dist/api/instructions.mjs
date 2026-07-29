async function instructions(imageAssets) {
  return await import('../chunks/instructions-resolver.mjs').then(({ resolveInstructions }) => resolveInstructions(imageAssets));
}

export { instructions };
