import { transformPlugin, preTransformPlugin } from './compiler/plugins.js';
import { createIndexer } from './indexer/index.js';
export const viteFinal = async (config, options) => {
    let { plugins = [], ...restConfig } = config;
    const { legacyTemplate = false } = options;
    if (legacyTemplate) {
        plugins.unshift(await preTransformPlugin());
    }
    plugins.push(await transformPlugin());
    return {
        ...restConfig,
        plugins,
    };
};
export const experimental_indexers = (indexers, options) => {
    return [createIndexer(options.legacyTemplate ?? false), ...(indexers || [])];
};
export const optimizeViteDeps = ['@storybook/addon-svelte-csf'];
