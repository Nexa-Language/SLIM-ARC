import * as universal from '../entries/pages/(chat)/chat/_id_/_page.ts.js';

export const index = 5;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/(chat)/chat/_id_/_page.svelte.js')).default;
export { universal };
export const universal_id = "src/routes/(chat)/chat/[id]/+page.ts";
export const imports = [];
export const stylesheets = [];
export const fonts = [];
