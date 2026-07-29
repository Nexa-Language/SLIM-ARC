

export const index = 3;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/settings/_layout.svelte.js')).default;
export const imports = [];
export const stylesheets = [];
export const fonts = [];
