function generateManifestIconsEntry(format, instruction) {
  const icons = { icons: [] };
  for (const icon of Object.values(instruction.transparent)) {
    icons.icons.push({
      src: icon.name,
      sizes: `${icon.width}x${icon.height}`,
      type: icon.mimeType
    });
  }
  for (const icon of Object.values(instruction.maskable)) {
    icons.icons.push({
      src: icon.name,
      sizes: `${icon.width}x${icon.height}`,
      type: icon.mimeType,
      purpose: "maskable"
    });
  }
  return format === "string" ? JSON.stringify(icons, null, 2) : icons;
}

export { generateManifestIconsEntry };
