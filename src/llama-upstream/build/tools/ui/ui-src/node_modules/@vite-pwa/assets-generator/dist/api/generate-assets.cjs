'use strict';

const node_fs = require('node:fs');
const promises = require('node:fs/promises');
const node_path = require('node:path');

async function generateAssets(instruction, overrideAssets, folder, log) {
  const transparent = Array.from(Object.values(instruction.transparent));
  await Promise.all(transparent.map((icon) => generateAsset("PNG", icon, folder, overrideAssets, log)));
  const maskable = Array.from(Object.values(instruction.maskable));
  await Promise.all(maskable.map((icon) => generateAsset("PNG", icon, folder, overrideAssets, log)));
  const apple = Array.from(Object.values(instruction.apple));
  await Promise.all(apple.map((icon) => generateAsset("PNG", icon, folder, overrideAssets, log)));
  const favicon = Array.from(Object.values(instruction.favicon));
  await Promise.all(favicon.filter((icon) => !icon.name.endsWith(".svg")).map((icon) => generateAsset("ICO", icon, folder, overrideAssets, log)));
  const appleSplashScreen = Array.from(Object.values(instruction.appleSplashScreen));
  await Promise.all(appleSplashScreen.map((icon) => generateAsset("PNG", icon, folder, overrideAssets, log)));
}
async function generateAsset(type, icon, folder, overrideAssets, log) {
  const filePath = node_path.resolve(folder, icon.name);
  if (!overrideAssets && node_fs.existsSync(filePath)) {
    log?.(`Skipping, ${type} file already exists: ${filePath}`, true);
    return;
  }
  await icon.buffer().then((b) => promises.writeFile(node_path.resolve(folder, icon.name), new Uint8Array(b))).then(() => {
  });
  log?.(`Generated ${type} file: ${filePath}`, false);
}

exports.generateAssets = generateAssets;
