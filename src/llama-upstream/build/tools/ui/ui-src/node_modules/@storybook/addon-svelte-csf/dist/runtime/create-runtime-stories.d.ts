import { type Component } from 'svelte';
import type { Cmp, ComponentAnnotations } from '../types.js';
/**
 * @module
 * Called from a bundler.
 *
 * It mounts the Stories components in a context which disables
 * the rendering of every `<Story />`,
 * but instead collects names and properties.
 *
 * For every discovered `<Story />`, it creates a `StoryFn` which
 * instantiate the main Stories component: Every Story but
 * the one selected is disabled.
 */
export declare const createRuntimeStories: (Stories: Component, meta: ComponentAnnotations<Cmp>) => Record<string, import("storybook/internal/csf").StoryAnnotations<import("@storybook/svelte").SvelteRenderer<Component<{
    Stories: Component;
    exportName: string;
    args: Record<string, any>;
    storyContext: import("../types.js").StoryContext<Cmp>;
    metaRenderSnippet?: import("svelte").Snippet;
}, {}, "">>, {
    Stories: Component;
    exportName: string;
    args: Record<string, any>;
    storyContext: import("../types.js").StoryContext<Cmp>;
    metaRenderSnippet?: import("svelte").Snippet;
}>>;
