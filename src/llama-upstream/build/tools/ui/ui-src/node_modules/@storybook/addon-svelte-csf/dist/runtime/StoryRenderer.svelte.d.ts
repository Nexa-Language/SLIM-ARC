import type { Component, Snippet } from 'svelte';
import type { Cmp, StoryContext } from '../types.js';
declare const StoryRenderer: Component<{
    Stories: Component;
    exportName: string;
    args: Record<string, any>;
    storyContext: StoryContext<Cmp>;
    metaRenderSnippet?: Snippet;
}, {}, "">;
export default StoryRenderer;
